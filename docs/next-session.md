# Next session

State as of 2026-08-30. Short by design — the protocol reference is
[docs/01v96i.md](01v96i.md), the capability inventory is
[docs/features.md](features.md), and the REAPER setup is
[docs/reaper.md](reaper.md).

## Where things stand

**Console ↔ bridge is complete.** Every message the 01V96i emits in normal use is
decoded — channels 1–32, ST-IN 1–4, aux sends and masters, buses, all four EQ bands on
channel/aux/master, solo, ATT, EQ on/off, and the console's status messages. Zero
unrecognised messages across ~12,600 captured. Everything decoded can also be *sent*,
with `tests/test_encoder_parity.py` proving encoder and parser agree, and `--sync` reads
the console's whole state at startup (~800 parameters in ~300 ms).

**REAPER works in both directions**, over OSC, on the console's normal mixing layer —
faders, mutes, solo, pan and master level. The REMOTE layer is not used. See
[docs/features.md](features.md) for the mapping table and the traps.

**Holophonix is untouched since the protocol work.** Aux sends, aux masters, bus faders,
bus/aux ON, solo, EQ on/off, the EQ filter enable and ATT all decode but have no
Holophonix addresses, so they are logged rather than sent.

## Next, in order

1. **Decide the Holophonix address scheme** for the controls above, plus the §5.2
   question — which Holophonix filter slot a band 1 HPF maps to. A decision, not code.
2. **Track banking in REAPER**, if more than 8 channels are used: whether `/track/20`
   addresses project track 20 or the 20th of an 8-track window is untested, because the
   test project had two tracks.
3. **ReaEQ**, if console EQ should drive REAPER. Reachable by slot (`hipass`, `loshelf`,
   `band/@`, `hishelf`, `lopass`); not implemented.
4. **Optional console coverage** if the scope becomes a general control surface:
   dynamics (gate/comp), aux send ON and pre/post, channel delay, phase, routing, scene
   recall (Program Change, a different message class), and the hypothesised bus EQ.

## Running it

```bash
source .venv/bin/activate
python3 main.py                                # detects console + REAPER, syncs, no flags
python3 tools/monitor.py                       # live decode and state view, logs JSONL
python3 tools/send_fader.py --channel 1 --db 0 # move a console fader
python3 -m unittest discover -s tests          # no hardware needed
```

Flags exist to override the discovery (`--backend`, `--ip`, `--port`, `--midi-in`,
`--midi-out`, `--listen-port`) but none are required.

## Things that will bite

- **Fader Resolution must be HIGH** on the console. LOW switches faders to 256 steps
  instead of 1024 and silently invalidates `FADER_LAW`, every dB reading and the golden
  snapshot. No error, just wrong numbers.
- **`tests/test_golden_dispatch.py`** replays 346 real captured messages and pins the
  resulting 215 OSC calls. Regenerate with `--update` only when a behaviour change is
  intended, and read the diff.
- **CI runs on every push** (`.github/workflows/tests.yml`): the suite on Linux across
  Python 3.13–3.14, plus one macOS and one Windows job to keep the cross-platform paths
  honest, and flake8. Python 3.13 and 3.14 only -- older versions were being
  tested to defend a compatibility claim nothing relied on. No test needs MIDI
  hardware.
- **The console does not echo** parameter changes it receives — it only reports moves
  made at its front panel. Silence after sending is normal; watch the console.
- **REAPER's OSC mode decides whether it talks back.** Receive-only means no feedback at
  all. Device IP/Port mode sends but binds an ephemeral local port, which is why the
  bridge reads REAPER's port from the socket table.
- **REAPER's master fader is not a dB scale.** `REAPER_FADER_LAW` in
  `backends/reaper.py` was measured from REAPER; re-measure if its fader range
  preference changes.
- **Port roles are console configuration**, not fixed. See [docs/01v96i.md](01v96i.md)
  § Console configuration.
