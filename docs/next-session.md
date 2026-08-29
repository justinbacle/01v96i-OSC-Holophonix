# Next session

State as of 2026-08-30, and what to do next. Short by design — the protocol
reference is [docs/01v96i.md](01v96i.md) and the long-range plan is
[docs/refactor-plan.md](refactor-plan.md).

## Where things stand

The console → OSC direction is complete and verified on hardware. Every message
the 01V96i emits in normal use is decoded: channels 1–32, ST-IN 1–4, aux sends
and masters, buses, all four EQ bands on channel/aux/master, solo, and the
console's own status messages. Zero unrecognised messages across ~12,600
captured.

The console ← bridge direction is proven but barely built: `tools/send_fader.py`
moves channel 1's motorised fader. `yamaha01v96i/encoder.py` has
`parameter_change()`, `parameter_request()` and a few helpers; `main.py` accepts
`--midi-out` but never sends.

Decoded but with nowhere to go: aux sends, aux masters, bus faders, bus/aux ON,
solo and the EQ filter enable have no Holophonix addresses yet, so they are
logged. That mapping is an open product decision, not a protocol gap.

## Next, in order

1. **Rx features.** Send mute, pan and EQ the way the fader already works. All
   are `parameter_change()` with a different element; the encoder is the mirror
   of the parser, so a message can be round-tripped through `parse()` before it
   goes out.
2. **`parameter_request()`.** Written, never fired at the console. Unknown:
   whether it is answered, on which port, and how fast requests can be issued
   back to back. This is what makes startup state sync possible — today the
   bridge is blind until something moves.
3. **Tx/Rx parity.** Anything the bridge can decode it should be able to send.
4. **Only then**, the DAW ports (USB 2–3 here), which speak Mackie Control /
   HUI. Possibly a better basis for the REAPER connector than SysEx — but that
   decision comes after parity.

## Running it

```bash
source .venv/bin/activate
python3 main.py --midi-in "MIDI 5" --midi-out "MIDI 4"   # Tx PORT in, Rx PORT out
python3 tools/monitor.py --port "MIDI 5"                 # live decode, logs JSONL
python3 tools/send_fader.py --channel 1 --db 0           # move a fader
python3 -m unittest discover -s tests                    # no hardware needed
```

## Things that will bite

- **Fader Resolution must be HIGH** on the console. LOW switches faders to 256
  steps instead of 1024 and silently invalidates `FADER_LAW`, every dB reading
  and the golden snapshot. No error, just wrong numbers.
- **`tests/test_golden_dispatch.py`** replays 346 real captured messages and
  pins the resulting 215 OSC calls. Regenerate with `--update` only when a
  behaviour change is intended, and read the diff.
- **The console does not echo** parameter changes it receives — it only reports
  moves made at its front panel. Silence after sending is normal; watch the
  console, not the wire.
- **Port roles are console configuration**, not fixed. See
  [docs/01v96i.md](01v96i.md) § Console configuration.
