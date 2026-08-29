# Handoff — 01v96i-OSC-Holophonix (next agent starts here)

Written at the end of a documentation/planning session. This file is the entry point: it
describes the current state, the rules, and the ordered task list. Everything referenced is
in this repository.

## Project context

MIDI→OSC bridge: a **Yamaha 01V96i** digital mixer (SysEx over MIDI) controls a
**Holophonix** spatial-audio engine (OSC over UDP). The owner's goal: keep the bridge
working, but make all 01v96i-specific knowledge reusable — a dedicated mixer API first,
then additional OSC backends (REAPER as a DAW control surface, ADM-OSC).

## Current state

- **Branch: `dev/misc_fixes`** (local, tracking `origin/dev/misc_fixes`, at `29aa894`;
  7 commits ahead of `main`). Relative to `main` it: fixes per-channel surround X/Y
  state, fixes the `eq()` NameError, dedupes the mask matcher, replaces prints with
  `logging`, adds argparse `--ip`/`--port`, and uses `MidiSysexListener` for the input
  loop. **Masks and value encodings are unchanged vs `main`** — the protocol doc below
  applies to both.
- **Uncommitted untracked work from the previous session** (written against `main`, still
  valid on this branch):
  - `docs/01v96i.md` — **authoritative** reverse-engineered SysEx reference: framing,
    header, two message forms, full message catalogue (masks + hex layouts), value
    encodings (tagged [obs]/[fit]/[hyp]), EQ band mapping, known quirks, verification
    checklist, code-location table.
  - `docs/device-validation.md` — on-device validation session plan (experiments V1–V13).
  - `docs/refactor-plan.md` — full refactor plan: `yamaha01v96i` package (events, decoder,
    parser) + `backends/` (holophonix / reaper / adm), migration steps, test vectors.
  - `tools/capture.py` — MIDI capture logger: annotates known messages using the masks in
    `main.py`, flags unknown ones, writes JSONL (see its docstring).
  - `tools/osc_dump.py` — stand-in OSC receiver that prints everything it receives.
  - `tests/test_capture_tool.py` — unittest suite for the capture tool.
  - ⚠ **These tools and tests were written but never executed** — the previous sandbox had
    no project dependencies. Running them is task 2.
- `notes/eq-implementation.md` (committed on this branch) — EQ notes that must be folded
  into `docs/01v96i.md` (task 3).
- README sections drafted in the previous session were **not yet applied** to this branch;
  ready-to-paste content is in the Appendix below.
- A backup of the discarded `main`-branch README edit exists at
  `/tmp/README.main-version.bak` (may not persist — the Appendix supersedes it).

## Environment & rules of engagement (owner's standing instructions)

- Machine: Ubuntu 26.04, system Python 3.14, no `ensurepip`/`pip`, no root.
  `python-rtmidi` cannot build here (no ALSA dev headers; no cp314 wheel).
- **The venv (`.venv/`, gitignored) is created by the owner.** If it does not exist, ask
  the owner to run the commands in the Appendix. **Never bootstrap pip/deps yourself and
  never work around sandbox limits — if you hit any blocker, stop and ask the owner.**
  (This is an explicit, repeated instruction from the owner.)
- No MIDI hardware in this environment. All device work goes through the owner using
  `docs/device-validation.md`.
- One commit per refactor step, tests green at each step. flake8 `max-line-length = 120`
  (`setup.cfg`).
- `docs/01v96i.md` is the single source of truth for protocol facts: update the doc
  first, then the code.
- Do not push without asking. Do not change observable bridge behaviour (OSC output)
  except as the refactor plan explicitly allows.

## Task list (in order)

### 0. Checkpoint commit

Commit the untracked `docs/`, `tools/`, `tests/` on this branch, e.g.
`git add docs tools tests && git commit -m "Add protocol reference, plans, capture tooling and tests"`.
(If the owner prefers to review first, ask.)

### 1. Merge the README sections (Appendix A)

Apply Appendix A to `README.md`: replace the Setup section (venv-based commands; keep the
branch's `--ip`/`--port` argparse table; drop the "OSC destination is currently
hardcoded" line), add the Development and Roadmap sections, and update the Project
structure tree (include `tools/`, `tests/`, `docs/`, and the final state of `notes/`).

### 2. Run the unexecuted tests (needs the owner's venv)

```bash
source .venv/bin/activate
python3 -m unittest discover -s tests -v
```

Fix anything that surfaces in `tools/capture.py` / `tests/test_capture_tool.py`. Then
smoke-test `python3 tools/osc_dump.py --port 4003` against
`osc/osc_sender.py` (send a few messages to 127.0.0.1). If the venv does not exist yet,
ask the owner to run the Appendix B commands and report back.

### 3. Reconcile `docs/01v96i.md` with this branch + fold the EQ notes

- Provenance header: state that the document describes `dev/misc_fixes`.
- **§5.2 EQ band mapping**: `notes/eq-implementation.md` gives Band 4 as Bell→6,
  Shelf→7, LPF (cut)→8 — this **contradicts** the older `main.py` code comment
  (cut→6, shelf→7, bell→8). Present the notes' version as the current intent, flag the
  contradiction explicitly, and add a verification item: decide the table against the
  actual Holophonix filter-slot configuration (which slots are HPF/shelf/bell/LPF).
- **§5.3**: add the notes' rival hypothesis — the band index may be encoded in bytes
  8/9 (currently wildcards in the `EQ_BAND_1` mask) — alongside the existing hypothesis
  (sequential `B5` = `0x21`–`0x23` for channel bands 2–4). Both are resolved by
  validation experiment V9.
- **§7 quirks**: mark as fixed on this branch: 7.1 (global X/Y state), 7.3 (`eq()`
  NameError), the matcher duplication; note 7.6 changed shape (unhandled messages are now
  `logging.warning`, still no persistence/annotation — `tools/capture.py` covers
  discovery). Keep the remaining quirks: vacuous/redundant mask checks, fader `u > 7`
  silently dropped, master EQ L/R collapsed, unknown EQ type codes silently read as Bell.
- **§9**: "Unhandled Sysex" is now `logging.warning` on this branch.
- **§10**: update the code-location table (no `match_mute_sysex`; `OSC_Handler` keeps
  per-channel X/Y dicts; `main()` uses argparse + `logging.basicConfig` +
  `MidiSysexListener`; `select_midi_port` still lives in `main.py`).
- Fold the remaining content of `notes/eq-implementation.md` into §5 (band-mapping table,
  handler status, "what needs doing" list), then replace `notes/eq-implementation.md` with
  a short stub pointing to `docs/01v96i.md` §5. Note: the notes' "14-bit signed value"
  phrasing is loose — the exact formula in §4.3 (`u·127+v` and its mirrored negative form)
  is authoritative.

### 4. Update `docs/device-validation.md`

- "What you need" / V12: no code editing needed anymore — run
  `python3 main.py --ip 127.0.0.1 --port 4003` against `tools/osc_dump.py`.
- V9: include both band-encoding hypotheses (sequential `B5` vs band index in bytes 8/9)
  and explicitly capture bytes 8–9 of every EQ message.
- Add a verification item for the §5.2 Band-4 type→slot contradiction.
- Note that the bridge now logs sent OSC at DEBUG level (visible on the console).

### 5. Update `docs/refactor-plan.md` for this branch's baseline

- §2 current-state problems: remove the items already fixed on this branch; the
  remaining problems are: `SysexHandler`/`OSC_Handler` coupling (decoding split across
  both layers), no tests for the bridge itself, no parser API/backends, EQ routing not
  wired, unhandled messages only logged, master EQ L/R collapsed, vacuous mask checks,
  `u > 7` drop.
- §6.1: the "one intentional deviation" (per-channel X/Y) is **obsolete** — this branch
  already fixed it. The golden baseline is this branch's behaviour; vector 11b becomes a
  normal parity case; parity claims must reference `logging` (not stdout prints).
- §7 CLI: build on the existing argparse (`--ip`/`--port`), adding `--backend`,
  `--midi-port`, `-v`; a bare `python3 main.py` must keep today's defaults.
- Migration step 9: do **not** delete `midi/midi_sysex.py` (it is the active listening
  loop on this branch) — evolve it instead.
- §6.1 Phase 2 EQ routing: incorporate the notes' design — keep per-channel, per-band
  last gain/frequency state and re-route to the correct Holophonix slot when the filter
  type changes.
- Add the port auto-detection idea from the branch's TODO comment as an optional feature
  (probe ports for `IGNORE_MESSAGE`, fall back to interactive selection).

### 6. On-device validation session (with the owner, when the mixer is connected)

Run `docs/device-validation.md` experiments V1–V13: the owner performs console actions;
you analyse the JSONL captures, upgrade [fit]/[hyp] tags to [obs] in `docs/01v96i.md`,
add new catalogue entries (EQ bands 2–4, Form B parameters, buses), and update the
refactor plan's constants if any formula changes (doc first, then code).

### 7. Execute the refactor

Follow `docs/refactor-plan.md` from migration step 1 (golden tests against the current
pipeline) through step 9. Then implement the REAPER backend (§6.2) and ADM-OSC (§6.3).

## Appendix A — README sections to merge

Replace the current `## Setup` section and add the following (keep the branch's
`--ip`/`--port` table; remove the "OSC destination is currently hardcoded" sentence):

```markdown
## Setup

Requires Python 3.10+ and a MIDI input the mixer is connected to.

​```bash
# One-time on Ubuntu/Debian: venv support, plus ALSA headers — python-rtmidi
# builds from source until wheels exist for your Python version (3.13+)
sudo apt install python3-venv libasound2-dev

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
​```

On startup you will be prompted to select a MIDI input port. Type `q` + Enter to quit.

​```bash
python3 main.py [--ip <address>] [--port <port>]
​```

| Argument | Default | Description |
| --- | --- | --- |
| `--ip` | `192.168.1.104` | OSC destination IP |
| `--port` | `4003` | OSC destination port |

## Development

With the venv active:

​```bash
python3 -m unittest discover -s tests -v   # run tests (no MIDI hardware needed)
python3 tools/capture.py --unknown-only     # log & annotate everything the mixer sends
python3 tools/osc_dump.py --port 4003       # print everything the bridge sends over OSC
​```

- `tools/capture.py` — MIDI capture logger for protocol discovery; known messages are
  annotated, unknown ones flagged (see docs/01v96i.md §9 and docs/device-validation.md).
- `tools/osc_dump.py` — stand-in OSC receiver to test the bridge end-to-end without a
  Holophonix unit: run it, then point the bridge at it with `--ip 127.0.0.1`.

## Roadmap

1. **On-device validation** — run the capture session in
   [docs/device-validation.md](docs/device-validation.md) once the mixer is connected, to
   firm up the reverse-engineered encodings and discover EQ bands 2–4.
2. **Refactor** — extract the 01v96i knowledge into a reusable mixer API with pluggable
   OSC backends, following [docs/refactor-plan.md](docs/refactor-plan.md).
3. **New backends** — REAPER control surface and ADM-OSC output on top of the new API.
```

(The zero-width escapes above mark the inner code fences — drop them when applying.)

Project structure tree to use:

```text
main.py                    # Application entry point; all MIDI→OSC logic
osc/osc_sender.py          # Thin UDP wrapper around python-osc
midi/midi_sysex.py         # MIDI SysEx listener used by the run loop
tools/capture.py           # MIDI capture & annotation logger (protocol discovery)
tools/osc_dump.py          # Stand-in OSC receiver for testing without Holophonix
tests/                     # Unit tests (run without MIDI hardware)
docs/01v96i.md             # Reverse-engineered 01V96i SysEx reference (authoritative)
docs/device-validation.md  # On-device validation plan (capture session protocol)
docs/refactor-plan.md      # Refactor plan: reusable 01v96i API + pluggable backends
requirements.txt
```

(Adjust the `notes/` line if task 3 replaces `notes/eq-implementation.md` with a stub.)

## Appendix B — venv setup (for the owner, on this machine)

```bash
sudo apt install python3-venv libasound2-dev
cd /home/jjj/Code/01v96i-OSC-Holophonix
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

(`libasound2-dev` is needed because `python-rtmidi` builds from source on Python 3.13+
until prebuilt wheels are published; unit tests themselves only need `mido` +
`python-osc`.)