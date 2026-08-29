# On-device validation plan — Yamaha 01V96i

A ready-to-run capture session for when the mixer is connected. Its job is to turn the
**[fit]** (empirically fitted) and **[hyp]** (hypothesis) items in
[docs/01v96i.md](01v96i.md) into **[obs]** (observed) facts, and to discover what is still
missing (EQ bands 2–4, the `0x1A` message form, buses beyond the 16 input channels).

Audience: whoever sits at the mixer (you) — plus any agent analysing the resulting logs.
No code changes are part of this session; findings are recorded and folded back into the
docs afterwards.

## What you need

- The mixer connected over USB-MIDI (or DIN via an interface) so a MIDI input port shows up.
- On the console, in the MIDI setup pages: device number = **1** (matches the observed
  `B1 = 0x10`) and parameter-change transmission enabled.
- The project environment set up (see README § Setup):
  `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Terminal A running the capture tool:

  ```bash
  python3 tools/capture.py              # interactive port selection, logs to captures/*.jsonl
  ```

  Use `python3 tools/capture.py --unknown-only` during discovery experiments (V6, V9, V10)
  so the console only shows messages the bridge does not understand yet. The JSONL file
  always records everything.
- For the end-to-end experiment (V12) only, terminal B:

  ```bash
  python3 tools/osc_dump.py --port 4003
  ```

  and point the bridge at it by setting `OSC_IP = "127.0.0.1"` / `OSC_PORT = 4003` in
  `main()` in `main.py` (currently around lines 484–485), then run `python3 main.py`.

## Method

- One control at a time. Nothing else moves.
- Discrete steps: hold each position ~1 s so the log is unambiguous.
- Note the wall-clock time of each step in the session log below (the JSONL has UTC
  timestamps; your notes link "what I touched" to "what arrived").
- Prefer separate log files per experiment: `python3 tools/capture.py --out captures/V2_pan.jsonl`.
- Total time: roughly 45–60 minutes for the full session.

## Experiments

Ordered by importance to the project. Each experiment lists: **Goal**, **Do**, **Expect**
(current belief, with confidence tags from docs/01v96i.md), **Record**, **Verdict** (how to
read the result and where it lands).

### V1 — Idle baseline (3 min)

- **Goal:** what the console emits when nothing is touched.
- **Do:** start a capture, don't touch anything for 3 minutes.
- **Expect:** only the 5-byte `F0 43 10 3E 1A 7F F7` message, annotated `ignore`.
- **Record:** how often it repeats (timestamps are in the log); anything else that appears.
- **Verdict:** other traffic → new entries in docs/01v96i.md §3. If nothing but the
  keepalive, upgrade its note to a timed observation.

### V2 — Pan encoding, negative side (top priority)

- **Goal:** settle the open question in §4.2 — the left side of the bipolar encoding.
- **Do:** on one channel, sweep PAN slowly with 1 s holds: centre → 25% right → 50% right →
  full right → centre → 25% left → 50% left → full left → centre. Repeat once.
- **Expect:** right side: `B8 = 0x00`, `B11` counts 0 (centre) → 63 (full right). Left side:
  `B8 = 0x7F`, `B11` **unknown range** — the current decoder assumes `value = B11/63 − 2`,
  which is only correct if the console sends `B11` 64…127 (≈127 centre, ≈64 full left).
- **Record:** the `(B8, B11)` pair at each hold point, especially just off centre and at
  full left. Check whether exact centre emits a distinct message.
- **Verdict:** if left side runs 64…127 → decoder confirmed, mark §4.2 **[obs]**. If it
  runs 1…63 (63 = full left) → the formula must change to roughly `−B11/63`; record the
  pairs, update §4.2 and the refactor plan's constants table.

### V3 — Surround X and Y encoding

- **Goal:** same question as V2 for the surround-pan X/Y parameters; plus how moves are
  reported.
- **Do:** hold Y still, sweep X centre → full + → full − → centre (with holds). Then swap:
  hold X still, sweep Y.
- **Expect:** axis sub-parameter `B6` = 5 (X) / 6 (Y); same sign/magnitude encoding as pan.
- **Record:** `(B8, B11)` pairs per axis; whether a single axis move emits one message or
  both X and Y together.
- **Verdict:** same rule as V2. The "one axis or both" answer matters for the
  `SurroundPosition` event design in docs/refactor-plan.md — note it down.

### V4 — Fader range, resolution, master slot

- **Goal:** confirm the 10-bit assumption (§4.1) and collect raw↔console-dB pairs.
- **Do:** on channel 1, set the fader at each console mark available (min, −60, −40, −30,
  −20, −10, −5, 0, +5, +10 / max) with 1 s holds. Then sweep the master fader slowly over
  its full range.
- **Expect:** `B10 (u)` never above 7; `raw = u·128 + v` in 0…1023. Master fader `B7`
  observed 0 or 1 (L/R slot).
- **Record:** raw values per console mark; master `B7` values seen.
- **Verdict:** `u > 7` ever seen → §7.5 is a real dropped-message bug and the masks must
  widen; note it. The raw↔dB pairs let a later backend fit the console's actual fader law
  (today's −60…+12 dB mapping is a Holophonix-range choice, not console data).

### V5 — Mutes: polarity and the two forms

- **Goal:** confirm mute value semantics and when each message form appears (§2, §3.3, §3.4).
- **Do:** mute/unmute channel 1 five times (1 s holds). Same on master. Then, if the console
  has MIDI/remote mode settings, switch the mode and repeat.
- **Expect:** `B11 ∈ {0, 1}` with **1 = unmuted** (sound on); both the `0x7F`-form and the
  `0x1A`-form may appear (README: "two SysEx variants (different mixer modes)").
- **Record:** which form(s) appear, in which console mode, and the `B11` values.
- **Verdict:** polarity confirmed → mark §3.3/§3.4 **[obs]**. Form presence per mode →
  document in §2. Anything beyond 0/1 → new finding, record the raw values.

### V6 — EQ band 1: gain encoding

- **Goal:** pin down the signed pair and the `±18 dB ↔ ±178 raw` scale (§4.3).
- **Do:** channel 1, band 1, bell type. Set gain to −18, −12, −6, 0, +6, +12, +18 dB (1 s
  holds).
- **Expect [fit]:** `B6 = 3`; `B10 = u`, `B11 = v`; positive `raw = u·127 + v` (u < 64),
  negative `raw = −((127−u)·127 + (127−v))`; `dB = 18·raw/178`.
- **Record:** `(u, v)` at each mark — **the zero point (0 dB) matters most**: it anchors the
  whole encoding.
- **Verdict:** if the marks don't fit the formula, tabulate raw↔dB from the captures and
  replace §4.3's formula (fit through the observed points). Either way, upgrade to **[obs]**
  with the table.

### V7 — EQ band 1: frequency encoding

- **Goal:** verify the single-byte logarithmic mapping (§4.3).
- **Do:** set band-1 frequency to the console's marks (lowest, 100, 315, 1k, 3.15k, 10k,
  highest).
- **Expect [fit]:** `B6 = 2`; `B11` ∈ 5…124 mapped 21.2 Hz → 20 kHz logarithmically;
  `B10` always 0 (ignored by the decoder).
- **Record:** `B11` (and `B10`) per mark.
- **Verdict:** endpoints + monotonicity confirmed → **[obs]**. A different `B10` value ever
  appearing → record it (the decoder ignores that byte today).

### V8 — EQ band 1: filter type / Q

- **Goal:** confirm the type codes and Q range (§4.3), and how type vs Q is reported.
- **Do:** cycle band-1 type through every option the console offers (cut/HPF variants,
  shelf, bell). In bell, sweep Q from minimum to maximum.
- **Expect [fit]:** `B6 = 1`; `B11` = 44 for HPF, 41 for shelf, otherwise bell with
  `Q = 10·(0.01)^(B11/40)` (0 → Q 10, 40 → Q 0.1).
- **Record:** `B11` for each type label; `B11` at Q extremes; whether changing type and
  changing Q produce distinguishable messages.
- **Verdict:** codes confirmed → **[obs]**. Unknown codes seen (not 41/44) → tabulate them;
  today they would be misread as Bell Q (§7.8).

### V9 — EQ bands 2–4 and master EQ (discovery — highest value)

- **Goal:** capture the parameter numbers for bands 2, 3, 4 and the master EQ (§3.7, §5.3).
- **Do:** run with `--unknown-only`. On channel 1, for each of bands 2, 3, 4: move gain,
  then frequency, then type/Q (1 s holds between controls). Then do the same on the master
  EQ (both L and R if the console exposes them separately).
- **Expect [hyp]:** same shape as band 1 but different `B5` (hypothesis: `0x21/0x22/0x23`
  for channel bands 2–4; master band 1 was `0x52`).
- **Record:** every UNKNOWN message, labelled with the control that produced it.
- **Verdict:** new entries in §3.7 (one subsection per band) + the hypothesis in §5.3
  confirmed or corrected. These become decoder table rows in the refactor.

### V10 — The `0x1A` message form (discovery)

- **Goal:** find out which console mode emits Form B and whether it carries more controls
  (§2).
- **Do:** if the console's MIDI/remote modes are identifiable, switch through them; in each,
  repeat a few basic moves (fader, mute, pan) and watch which form arrives.
- **Expect:** today only the mutes are known in Form B (`0x5A` channel, `0x5E` master).
- **Record:** per mode, which controls arrive in which form; any UNKNOWN `43 10 3E 1A …`
  messages.
- **Verdict:** extend §2's form description and the catalogue with new Form B entries.

### V11 — Channel coverage and other layers

- **Goal:** confirm `B7` = 0…15 for channels 1–16 and see whether other layers emit SysEx.
- **Do:** brush every channel fader once (1–16, in order). Then, if the console has aux /
  bus / remote layers, move one control on each layer.
- **Expect:** channel messages with `B7` 0…15 only.
- **Record:** any message with `B7` > 15, different parameter bytes, or from other layers.
- **Verdict:** confirm §6, or extend the catalogue (buses/auxes are candidate future
  mappings for other backends).

### V12 — End-to-end bridge check

- **Goal:** verify the full path with `osc_dump.py` as the OSC target.
- **Do:** with terminal B (`tools/osc_dump.py`) running and `main.py` pointed at
  `127.0.0.1:4003`, move each mapped control: a channel fader, master fader, pan, surround
  X then Y, mute, master mute, EQ band-1 gain/freq/Q.
- **Expect:** the addresses and value ranges from the README's OSC mapping table (gain
  −60…+12 dB, azim ±45°, polar azim/dist, mute 0/1).
- **Record:** every printed line (address + value); note anything surprising — full-left pan
  will directly expose the V2 question live.
- **Verdict:** deviations → new §7 entries in docs/01v96i.md and follow-ups in the refactor
  plan. Restore `OSC_IP` in `main.py` afterwards.

### V13 — Message rate / interpolation (optional)

- **Goal:** know what a fast move looks like on the wire (bursts? interpolated values?
  final-settle message?).
- **Do:** one fast full fader throw; one slow full throw.
- **Record:** message counts per throw in the JSONL (timestamps make this easy).
- **Verdict:** informative only — backend throttling/batching decisions later.

## Session log

Copy this block per experiment and fill it in (keep raw byte dumps in the JSONL files;
reference them by filename):

```markdown
### <experiment id> — <name>  (log: captures/<file>.jsonl)
| Time | Action on console | Bytes seen (hex) | Note |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

**Conclusion:** …
**Doc updates:** docs/01v96i.md §…
```

## After the session — folding results back

1. Update [docs/01v96i.md](01v96i.md): upgrade **[fit]/[hyp]** tags to **[obs]**, add new
   catalogue entries (§3), correct formulas (§4), tick off §8's checklist.
2. Keep the JSONL captures — they are the natural fixtures for the refactor's regression
   tests (see [docs/refactor-plan.md](refactor-plan.md), test strategy). `captures/` is
   gitignored, so curate any file you want to keep into `tests/fixtures/` later.
3. If an encoding changed (most likely V2 pan or V6 EQ gain), update the constants in the
   refactor plan's decoder spec **before** implementation starts — doc first, code second.
4. Open follow-ups in the README's implementation status for anything discovered but not
   wired (new parameters, buses, modes).