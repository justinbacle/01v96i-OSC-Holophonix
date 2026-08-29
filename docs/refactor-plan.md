# Refactor plan — reusable 01V96i mixer API + pluggable OSC backends

**For the implementing agent.** This plan is self-contained, but
[docs/01v96i.md](01v96i.md) (the reverse-engineered SysEx reference) is mandatory reading —
it is the single source of truth for every byte layout and value encoding used below. Do not
change observable behaviour except for the one intentional deviation listed in §6.

## 1. Context

The repo is a MIDI→OSC bridge: a **Yamaha 01V96i** mixer (SysEx over MIDI) controls a
**Holophonix** spatial-audio engine (OSC over UDP). Everything currently lives in
`main.py` (~530 lines): SysEx masks, value decoding, Holophonix address mapping, dispatcher,
port selection and the run loop.

**Goal of this refactor:** make the 01v96i layer a reusable, transport-agnostic API so the
same physical surface can drive other OSC targets — ADM-OSC (open standard) and **REAPER**
(as a DAW control surface) — by adding a backend, not by touching mixer code.

### Working rules

- One commit per migration step (§9), tests green at each step.
- If you hit an environment blocker (missing dependency, sandbox limit), **stop and ask the
  owner** — do not work around it.
- Hardware-in-the-loop verification is done by the owner (see docs/01v96i.md §9);
  your tests must not require MIDI hardware.

## 2. Current-state problems

1. `SysexHandler` (01v96i parsing) and `OSC_Handler` (Holophonix mapping) are coupled:
   decoding is split across both (sign/magnitude in the former; dB scaling, azimuth/
   distance trig and mute polarity inversion in the latter).
2. X/Y surround state is **global** instead of per-channel — an X move on channel A
   followed by a Y move on channel B produces B's event computed from A's X
   (docs/01v96i.md §7.1).
3. Master EQ L/R slots are collapsed; latent `NameError` in `eq()`; vacuous mask checks;
   three copies of the same mask matcher (§7.2–7.6).
4. No tests; no capture tooling (this has since been added: `tools/capture.py`,
   `tools/osc_dump.py`, `tests/test_capture_tool.py`).
5. `midi/midi_sysex.py` is dead code (defined, never used).

## 3. Target architecture

```text
main.py                  # thin CLI: args → backend + parser + midi loop (UX unchanged)
yamaha01v96i/            # THE 01v API — pure, no mido/OSC imports
    __init__.py          #   exports: parse/Parser, events, errors
    events.py           #   MixerEvent dataclasses (semantic, normalized values)
    decoder.py           #   byte tables + value decoders (docs/01v96i.md §3/§4)
    parser.py            #   Yamaha01v96iParser: raw SysEx → events; on_unknown hook
backends/
    __init__.py          #   Backend protocol + registry
    holophonix.py        #   today's behaviour (see §6 parity table)
    reaper.py            #   Phase 2: REAPER OSC control surface
    adm_osc.py           #   Phase 3: ADM-OSC output mode
midi/
    ports.py            #   port listing + interactive selection (moved from main.py)
osc/
    osc_sender.py        #   unchanged (already generic)
tools/                   # unchanged (capture.py, osc_dump.py); capture imports switch to yamaha01v96i
tests/                   # test_capture_tool.py exists; add decoder/parser/backend tests
```

**Architecture rules (enforced by grep in the acceptance criteria, §11):**

- No 01v96i protocol knowledge outside `yamaha01v96i/` (headers, parameter bytes, raw-value
  scalings). Backends only ever see normalized events.
- No OSC address strings for a target outside that target's backend module (and its tests).
- `yamaha01v96i` imports nothing from `mido`, `pythonosc`, `backends`, `midi`, `osc` — it is
  pure functions over `list[int]`.

## 4. Event model (`yamaha01v96i/events.py`)

All events are frozen dataclasses. Every event carries `raw: tuple[int, ...]` (the full
SysEx payload as seen) so captures can be replayed and encodings re-derived without losing
information.

```python
@dataclass(frozen=True)
class MixerEvent:
    """Base class for all events emitted by the 01v96i parser."""
    raw: tuple[int, ...]

@dataclass(frozen=True)
class ChannelEvent(MixerEvent):
    channel: int          # 0-based, console channels 1–16 (docs/01v96i.md §6)

@dataclass(frozen=True)
class FaderMoved(ChannelEvent):
    value: float          # normalized 0.0–1.0 (raw/1023); NOT dB — backends scale
    raw_value: int        # 0–1023

@dataclass(frozen=True)
class MasterFaderMoved(MixerEvent):
    value: float          # normalized 0.0–1.0
    raw_value: int
    slot: int             # observed 0/1 (L/R) — see docs/01v96i.md §3.2

@dataclass(frozen=True)
class ChannelMuted(ChannelEvent):
    muted: bool           # mixer truth: data[11] == 0 → muted (§3.3)

@dataclass(frozen=True)
class MasterMuted(MixerEvent):
    muted: bool
    slot: int

@dataclass(frozen=True)
class Panned(ChannelEvent):
    value: float          # −1.0 … +1.0, positive = right (§4.2)

@dataclass(frozen=True)
class SurroundPosition(ChannelEvent):
    """Emitted on either axis change; parser keeps per-channel last X/Y."""
    x: float              # −1.0 … +1.0
    y: float              # −1.0 … +1.0

@dataclass(frozen=True)
class EqChanged(ChannelEvent):
    """Master EQ uses a separate subclass (channel=None is not expressible here)."""
    band: int             # 1–4
    gain_db: float | None = None      # ±18 dB (§4.3)      — when B6 == 3
    freq_hz: float | None = None      # 21.2 Hz–20 kHz     — when B6 == 2
    q: float | None = None            # 0.1–10             — when B6 == 1 and bell
    filter_type: str | None = None    # 'HPF' | 'SHELF' | 'BELL' | 'UNKNOWN'

@dataclass(frozen=True)
class MasterEqChanged(EqChanged):
    slot: int = 0         # observed 0/1 (L/R) — currently collapsed by the Holophonix backend
```

Design notes:

- **Normalized values, mixer truth.** Faders are 0–1 floats (not dB); pan/X/Y are −1..+1;
  mutes are booleans. Each backend applies its own scaling and polarity — e.g. Holophonix
  sends `mute = 1` when `muted is True`, REAPER's `/track/N/mute` also uses 1 = muted.
- **Why `SurroundPosition` merges axes:** the console reports X and Y as separate SysEx
  messages (§3.6); azimuth/distance is a *target* concept. The parser tracks last-known
  X/Y per channel and emits one event per change. This is also the intentional fix for
  §7.1 (see §6).
- **`EqChanged`** carries optional fields because the console reports type and Q in one
  message (§4.3): a bell message sets both `filter_type='BELL'` and `q`; HPF/shelf set only
  `filter_type`. `UNKNOWN` (raw code not 41/44) must be surfaced explicitly, not silently
  treated as Bell (fixes §7.8).

## 5. Decoder spec (`yamaha01v96i/decoder.py`)

Table-driven. One row per known message, in the **exact order** of `main()`'s current
dispatcher registration (first match wins — preserve it):

```python
@dataclass(frozen=True)
class MessageSpec:
    name: str                     # 'channel_fader', 'channel_mute_form_a', ...
    mask: tuple                    # same semantics as today: int = fixed byte,
                                   # str = named capture slot, None = wildcard
    decode: Callable[[list[int]], MixerEvent | None]
```

Masks and parameter numbers are copied verbatim from docs/01v96i.md §3 (they are identical
to `main.py` today). Consolidate the three matcher copies (`match_sysex`,
`match_mute_sysex`, the inline loops) into **one** matcher — `None` and `str` both mean
"unchecked", ints must match; this is a superset of today's behaviour.

**Constants (single place, cross-referenced to the doc; update the doc first if the device
validation session changes any of them):**

| Constant | Value | Doc ref |
| --- | --- | --- |
| `MANUFACTURER_YAMAHA` | `0x43` | §2 |
| `DEVICE_NUMBER` | `0x10` | §2 |
| `MODEL_01V96I` | `0x3E` | §2 |
| `FORM_A`, `FORM_B` | `0x7F`, `0x1A` | §2 |
| `FADER_FULL_SCALE` | `1023` | §4.1 |
| `BIPOLAR_POS_MAX` | `63` | §4.2 |
| `EQ_GAIN_FULL_SCALE` | `178` | §4.3 |
| `EQ_GAIN_MAX_DB` | `18.0` | §4.3 |
| `EQ_FREQ_MIN_HZ` / `MAX_HZ` | `21.2` / `20000.0` | §4.3 |
| `EQ_FREQ_RAW_MIN` / `RAW_MAX` | `5` / `124` | §4.3 |
| `EQ_TYPE_HPF` / `EQ_TYPE_SHELF` | `44` / `41` | §4.3 |
| `EQ_Q_RAW_MAX` | `40` | §4.3 |

Decode functions implement §4 exactly (formulas reproduced there; keep them in sync).
`Yamaha01v96iParser` (parser.py):

```python
class Yamaha01v96iParser:
    def __init__(self, on_unknown: Callable[[list[int]], None] | None = None): ...
    def parse(self, data: list[int]) -> list[MixerEvent]:
        """Match against specs in order; first match wins; [] for ignore/no-op.
        Unknown messages invoke on_unknown (default: log WARNING with hex dump)
        instead of printing to stdout."""
```

The parser keeps `_surround: dict[int, tuple[float, float]]` (per-channel x/y) and emits
`SurroundPosition` on X or Y messages. Expose `snapshot()` returning current channel states
(foundation for future bidirectional sync — do not build more than that).

## 6. Backend spec

Protocol (backends/__init__.py):

```python
class Backend(Protocol):
    name: str
    def on_event(self, event: events.MixerEvent) -> None: ...
```

### 6.1 Holophonix backend — behaviour parity table (Phase 1)

Every conversion must reproduce today's `OSC_Handler` exactly:

| Event | Address | Value |
| --- | --- | --- |
| `FaderMoved` | `/track/{ch+1}/gain` | `72*value − 60` (−60…+12 dB) |
| `MasterFaderMoved` | `/master/gain` | `72*value − 60` |
| `ChannelMuted` | `/track/{ch+1}/mute` | `1 if muted else 0` |
| `MasterMuted` | `/master/mute` | `1 if muted else 0` |
| `Panned` | `/track/{ch+1}/azim` | `45 * value` |
| `SurroundPosition` | `/track/{ch+1}/azim` then `/track/{ch+1}/dist` | `degrees(atan2(x*10, y*10))` and `hypot(x*10, y*10)` |
| `EqChanged` (gain) | `/track/{ch+1}/equalizer/filter/{band}/gain` | `gain_db` |
| `EqChanged` (freq) | `/track/{ch+1}/equalizer/filter/{band}/freq` | `freq_hz` |
| `EqChanged` (q) | `/track/{ch+1}/equalizer/filter/{band}/q` | `q` |
| `MasterEqChanged` (same) | `/master/equalizer/filter/{band}/...` | same values |

EQ band routing, Phase 1 (parity — preserves today's actual behaviour):
gain/freq → slot **1** regardless of type; Q → slot **3**, bell only (matches current code,
including its incompleteness). Phase 2 implements the documented intent (docs/01v96i.md
§5.2: HPF→1, shelf→2, bell→3, band 2→4, band 3→5, band 4→6/7/8) as a separate commit with
its own tests, after parity is proven.

**The one intentional behaviour deviation in Phase 1:** X/Y state is per-channel (§4),
fixing docs/01v96i.md §7.1. Everything else — including stdout print format — stays
byte-identical; a test must document this change (see §10, vector 11b).

### 6.2 REAPER backend (Phase 2)

Target: REAPER's default OSC surface ("Control/OSC/web → Add → OSC", pattern
`Default.ReaperOSC`, listen on a chosen port; the bridge sends to it):

| Event | Address | Value |
| --- | --- | --- |
| `FaderMoved` | `/track/{ch+1}/volume` | `value` (0–1 float — direct fit) |
| `MasterFaderMoved` | `/master/volume` | `value` |
| `ChannelMuted` | `/track/{ch+1}/mute` | `1 if muted else 0` |
| `MasterMuted` | `/master/mute` | `1 if muted else 0` |
| `Panned` | `/track/{ch+1}/pan` | `value` (−1…+1) |

Surround/EQ: no natural REAPER mapping — log at DEBUG and ignore. Document the 16-channel
limitation; bank switching is explicitly out of scope. Note in the backend docstring that
REAPER must be configured to listen on the port the bridge sends to.

### 6.3 ADM-OSC backend (Phase 3)

Per the README's spec: `/adm/obj/{n}/x`, `/adm/obj/{n}/y` (−1…1) from `SurroundPosition`;
polar mode `/adm/obj/{n}/azim` + `/dist`; `/adm/obj/{n}/gain` as linear `10**((72*v−60)/20)`.

## 7. `main.py` / CLI spec

```text
python3 main.py [--backend holophonix|reaper|adm] [--host IP] [--port N]
                [--midi-port NAME] [-v]
```

- Defaults **must preserve today's behaviour**: `--backend holophonix`,
  `--host 192.168.1.104`, `--port 4003`. This removes the "hardcoded" complaint without
  changing what a bare `python3 main.py` does.
- Keep the UX: interactive port selection (moved to `midi/ports.py`, imported), `q` + Enter
  to quit, the same startup prints.
- Wire-up: `mido` loop → `parser.parse(msg.data)` → `for event in events: backend.on_event(event)`.

## 8. Test strategy

- **Black-box golden tests** (tests/test_bridge_golden.py): feed recorded byte sequences
  into the *running pipeline* (today: `SysexDispatcher` + `OSC_Handler` with a mock
  `OSCSender` that records sends; after the refactor: parser + backend with the same mock)
  and assert address+value pairs. Write these **before** touching `main.py` (step 0 below)
  so parity is provable, not assumed.
- **Decoder unit tests** (tests/test_decoder.py): the vectors in §9 plus edge cases: pan
  sign byte other than 0/127 → 0.0 + warning; fader `u = 8` → mask rejects (documents §7.5);
  EQ type code not in {41, 44} → `filter_type='UNKNOWN'`, no Q.
- **Parser tests**: mask-order precedence, `on_unknown` invocation, per-channel X/Y state.
- **Fixtures**: JSONL files captured with tools/monitor.py (docs/01v96i.md §9
  "after the session") can be replayed as regression data — add `tests/fixtures/`.
- Run: `python3 -m unittest discover -s tests -v` with the venv active (README § Development).

## 9. Test vectors (input bytes → events → Holophonix OSC)

Derived from the current code's formulas on 2026-05-18 — **re-derive against the running
code when implementing**; do not trust this table blindly. Expected event values use the
§4 semantics; `ch` is 0-based.

| # | Bytes (decimal payload) | Event | Holophonix OSC |
| --- | --- | --- | --- |
| 1 | `[67,16,62,127,1,28,0,2,0,0,5,13]` | `FaderMoved(ch=2, value≈0.6383, raw=653)` | `/track/3/gain` ≈ −14.041 |
| 2 | `[67,16,62,127,1,28,0,0,0,0,0,0]` | `FaderMoved(ch=0, value=0.0, raw=0)` | `/track/1/gain` −60.0 |
| 3 | `[67,16,62,127,1,28,0,15,0,0,7,127]` | `FaderMoved(ch=15, value=1.0, raw=1023)` | `/track/16/gain` 12.0 |
| 4 | `[67,16,62,127,1,79,0,0,0,0,7,127]` | `MasterFaderMoved(value=1.0, raw=1023, slot=0)` | `/master/gain` 12.0 |
| 5 | `[67,16,62,127,1,26,0,4,0,0,0,0]` | `ChannelMuted(ch=4, muted=True)` | `/track/5/mute` 1 |
| 6 | `[67,16,62,26,4,90,0,4,0,0,0,1]` | `ChannelMuted(ch=4, muted=False)` | `/track/5/mute` 0 |
| 7 | `[67,16,62,127,1,77,0,0,0,0,0,0]` | `MasterMuted(muted=True, slot=0)` | `/master/mute` 1 |
| 8 | `[67,16,62,127,1,27,0,4,0,0,0,63]` | `Panned(ch=4, value=1.0)` | `/track/5/azim` 45.0 |
| 9 | `[67,16,62,127,1,27,0,4,127,0,0,64]` | `Panned(ch=4, value≈−0.9841)` (pending V2!) | `/track/5/azim` ≈ −44.286 |
| 10 | `[67,16,62,127,1,37,5,4,0,0,0,63]` | `SurroundPosition(ch=4, x=1.0, y=0.0)` | `/track/5/azim` 90.0, `/track/5/dist` 10.0 |
| 11 | `[67,16,62,127,1,37,6,4,0,0,0,31]` (after #10) | `SurroundPosition(ch=4, x=1.0, y≈0.4921)` | `/track/5/azim` ≈ 63.85, `/dist` ≈ 11.146 |
| 11b | #10 then `[67,16,62,127,1,37,6,4,1,0,0,31]` (Y on ch 2) | `SurroundPosition(ch=1, x=0.0, y≈0.4921)` | **differs from today** (today would use ch 5's x) — the intentional §7.1 fix |
| 12 | `[67,16,62,127,1,32,3,2,0,0,1,51]` | `EqChanged(ch=2, band=1, gain_db=18.0)` | `/track/3/equalizer/filter/1/gain` 18.0 |
| 13 | `[67,16,62,127,1,32,3,2,0,0,126,76]` | `EqChanged(ch=2, band=1, gain_db=−18.0)` | `/track/3/equalizer/filter/1/gain` −18.0 |
| 14 | `[67,16,62,127,1,32,2,2,0,0,0,64]` | `EqChanged(ch=2, band=1, freq_hz≈632.8)` | `/track/3/equalizer/filter/1/freq` ≈ 632.8 |
| 15 | `[67,16,62,127,1,32,1,2,0,0,0,20]` | `EqChanged(ch=2, band=1, filter_type='BELL', q=1.0)` | `/track/3/equalizer/filter/3/q` 1.0 |
| 16 | `[67,16,62,127,1,82,3,0,0,0,1,51]` | `MasterEqChanged(band=1, gain_db=18.0, slot=0)` | `/master/equalizer/filter/1/gain` 18.0 |
| 17 | `[67,16,62,26,127]` | (ignored, no event) | — |
| 18 | `[67,16,62,127,9,1,0,0,0,0,0,0]` | no match → `on_unknown` | — |

Assert floats with a tolerance (e.g. `assertAlmostEqual(..., places=3)`), not exact
equality.

## 10. Migration steps (one commit each)

1. **Baseline golden tests.** With `main.py` untouched, add
   `tests/test_bridge_golden.py` driving `SysexDispatcher` + `OSC_Handler` with a mock
   `OSCSender` (records `send()` calls) and the §9 vectors (skip 11b — it documents the
   old bug; add it as an `expectedFailure` or skip with a comment). All green.
2. **Package skeleton.** Create `yamaha01v96i/` with `events.py` implemented + unit tests
   for the dataclasses. No wiring changes.
3. **Decoder + parser.** Implement `decoder.py` and `parser.py` per §5 with masks copied
   verbatim; add `tests/test_decoder.py` and `tests/test_parser.py` (vectors §9 + edge
   cases). `main.py` untouched still.
4. **Holophonix backend.** Implement `backends/holophonix.py` per §6.1; adapt the golden
   tests to run against parser+backend (keep them passing against `main.py`'s pipeline in
   the same commit to prove parity). Vector 11b flips from expectedFailure to passing —
   the one intentional deviation.
5. **Rewire `main.py`.** CLI per §7, `midi/ports.py` extracted, run loop → parser+backend.
   Delete `SysexHandler`/`OSC_Handler`/`SysexDispatcher` from `main.py`. Point
   `tools/capture.py`'s `KNOWN_MESSAGES` import at `yamaha01v96i` (annotation names should
   match the spec names); `tests/test_capture_tool.py` should keep passing with updated
   expected labels if names changed.
6. **Backend registry + stubs.** `backends/__init__.py` registry, `--backend` flag,
   `reaper.py` and `adm_osc.py` stubs (constructible, `on_event` logs at DEBUG).
7. **REAPER backend** (if green-lit): §6.2 mappings + tests with the mock sender.
8. **Docs.** README (usage, structure, backend table), docs/01v96i.md §10 "where this
   lives in the code" table, append an implementation log section to this file.
9. **Cleanup.** Delete `midi/midi_sysex.py` (dead code, superseded by `yamaha01v96i` +
   `midi/ports.py`).

## 11. Acceptance criteria

- `python3 -m unittest discover -s tests` fully green with the venv active.
- `python3 main.py` unchanged UX and identical OSC output for all §9 vectors (golden tests).
- Architecture rules hold:
  - `grep -rn "43\|62\|127" --include=*.py yamaha01v96i` finds protocol constants **only**
    inside `yamaha01v96i/` and its tests (spot-check: no raw `67, 16, 62` masks elsewhere).
  - `grep -rn "/track/\|/master/" --include=*.py` hits only `backends/`, `tests/`, docs.
  - `grep -rn "atan2\|1023\|\* 72" --include=*.py` hits only `backends/holophonix.py` and
    `yamaha01v96i/decoder.py` (their respective constants).
- `python3 tools/capture.py` and `python3 tools/osc_dump.py` still run (capture annotations
  now sourced from `yamaha01v96i`).
- README and docs/01v96i.md §10 updated.

## 12. Environment notes (for agents in this workspace)

- System Python is 3.14 without `ensurepip`/`pip`; the project venv (`.venv/`, gitignored)
  is created by the owner per README § Setup. **Never bootstrap your own pip/deps
  workarounds** — ask the owner to run the setup commands instead.
- `python-rtmidi` may need to build from source on Python ≥3.13 (no wheel yet); on
  Ubuntu 26.04 that requires `libasound2-dev` (see README § Setup). Unit tests do not
  need rtmidi — only `mido` + `python-osc` — so run them via
  `source .venv/bin/activate && python3 -m unittest discover -s tests`.
- The console is not connected in this environment; anything hardware-related goes
  through the owner (docs/01v96i.md §9).

## 13. Out of scope (explicitly)

- Bidirectional sync (mixer ← OSC state), beyond the parser `snapshot()` hook.
- Bank/layer switching for >16 channels (REAPER backend note).
- Config file persistence for host/port (CLI flags are enough for this phase).
- EQ bands 2–4 and any parameter not yet captured — they enter as new rows in the decoder
  table after on-device verification, not as speculative code.