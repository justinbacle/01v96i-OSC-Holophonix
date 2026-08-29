# 01v96i-OSC

A MIDI-to-OSC bridge that translates control surface input from a **Yamaha 01v96i digital mixer**
into OSC messages for a **Holophonix immersive audio system**.

The mixer acts as a physical control surface: faders, pan knobs, mutes, surround pan controls,
and EQ parameters are all captured via MIDI SysEx and forwarded as OSC commands to Holophonix
for spatial audio control.

## How it works

1. The application listens for MIDI SysEx messages from the Yamaha 01v96i.
2. Each message is matched against a set of registered patterns (masks).
3. On match, a handler converts the raw MIDI value into the appropriate OSC parameter and sends
   it to the Holophonix host over UDP.

## Setup

Requires Python 3.10+ and a MIDI input the mixer is connected to.

```bash
# One-time on Ubuntu/Debian: venv support, the Python headers and ALSA headers.
# python-rtmidi builds from source until wheels exist for your Python version.
sudo apt install python3-venv python3-dev libasound2-dev

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

On startup you will be prompted to select a MIDI input port. Type `q` + Enter to quit.

The console exposes eight USB-MIDI ports; **MIDI 1** is the one to pick. It carries
everything, while the console's configured Tx Port carries only a subset and moves if that
setting changes.

### Console settings

On the console itself (full detail and rationale in
[docs/01v96i.md](docs/01v96i.md) § Console configuration):

- `MIDI` → `[F1]`: **PARAMETER CHANGE Tx = ON** (to read the console), **Rx = ON** (to
  drive it), **ECHO = off**, and **CHANNEL Tx/Rx = 1**.
- `MIDI` → `[F1]`: **Fader Resolution = HIGH**. On LOW the faders drop to 256 steps and
  every dB value the bridge reports will be wrong.
- `DIO/SETUP` → `MIDI/Host`: note which USB port is assigned to **Studio Manager** — that
  is the port to give the bridge. It carries the full stream in both directions, and is
  *not* the Rx/Tx PORT setting.

```bash
python3 main.py [--ip <address>] [--port <port>]
```

| Argument | Default | Description |
| --- | --- | --- |
| `--ip` | `192.168.1.104` | OSC destination IP |
| `--port` | `4003` | OSC destination port |

## OSC address mapping

| Mixer control | OSC address | Value range |
| --- | --- | --- |
| Channel fader | `/track/{n}/gain` | −∞ to +10 dB |
| Channel mute | `/track/{n}/mute` | 0 / 1 |
| Channel pan | `/track/{n}/azim` | −45 to +45° |
| Surround X/Y | `/track/{n}/azim` + `/track/{n}/dist` | polar coords |
| Master fader | `/master/gain` | −∞ to 0 dB |
| Master mute | `/master/mute` | 0 / 1 |
| EQ gain | `/track/{n}/equalizer/filter/{b}/gain` | −18 to +18 dB |
| EQ frequency | `/track/{n}/equalizer/filter/{b}/freq` | 21.2 Hz – 20 kHz |
| EQ Q | `/track/{n}/equalizer/filter/{b}/q` | — |

`n` = track number (1-based), `b` = EQ band index.

---

## Implementation status

### Done

- **Channel faders** — all 16 channels; 10-bit position index → dB via a measured fader law
- **Master fader** — same law, ending at unity instead of +10 dB
- **Channel and master mute** — both the edit-buffer and backup-memory forms, which the
  console emits together for every press
- **Pan (L/R)** — the console's own −63…+63 value, mapped to ±45° azimuth
- **Surround X/Y** — per-channel X/Y state → azimuth + distance (polar)
- **EQ, all four bands** — gain, frequency, Q and filter type, plus the HPF/LPF enable that
  bands 1 and 4 send in place of a gain
- **MIDI port selection** — interactive on startup
- **OSC transport** — UDP via `python-osc`

### Decoded but not sent

These are fully decoded and logged, but have no Holophonix address yet — the mapping is
undecided (see [docs/01v96i.md](docs/01v96i.md) §5.2):

- **Aux sends and aux masters**, **bus faders**, **bus/aux ON**
- **Solo**
- **EQ filter enable** for bands 1 and 4

### Not yet implemented

- **ADM-OSC position mode** — alternative output mode using the
  [ADM-OSC](https://github.com/immersive-audio-live/ADM-OSC) open standard instead of the
  proprietary Holophonix addresses. Requires:
  - Cartesian output: `/adm/obj/{n}/x`, `/adm/obj/{n}/y` (range −1 to 1) from mixer surround X/Y
  - Polar output: `/adm/obj/{n}/azim`, `/adm/obj/{n}/dist` (azimuth −180 to 180°, distance 0 to 1)
  - Gain: `/adm/obj/{n}/gain` (linear 0–1) instead of dB
  - A runtime mode switch (Holophonix vs ADM-OSC) so both targets can be supported
- **Configuration file** — OSC host/port are settable with `--ip`/`--port` but not persisted
- **Other mixer parameters** — compressor, gates, reverb sends, aux routing, etc. (scope TBD)
- **Bidirectional sync** — no state received from Holophonix; mixer position is not updated on connect

## Project structure

```text
main.py                    # CLI and wiring only
yamaha01v96i/              # The 01V96i protocol API - no MIDI or OSC dependencies
    protocol.py            #   framing, value encoding, fader laws, EQ tables
    events.py              #   semantic events backends consume
    parser.py              #   message table; raw SysEx -> events
backends/holophonix.py     # Holophonix OSC addresses (the only place they live)
midi/ports.py              # Port listing, selection, keepalive detection
midi/midi_sysex.py         # MIDI SysEx listener used by the run loop
osc/osc_sender.py          # Thin UDP wrapper around python-osc
tools/monitor.py           # Live TUI: decodes the console's SysEx as you move controls
tools/capture.py           # Bulk MIDI capture & annotation logger
tools/osc_dump.py          # Stand-in OSC receiver for testing without Holophonix
tests/                     # Unit tests + golden OSC snapshot (no MIDI hardware needed)
docs/01v96i.md             # Reverse-engineered 01V96i SysEx reference (authoritative)
docs/refactor-plan.md      # Refactor plan: reusable 01v96i API + pluggable backends
requirements.txt
```

## Development

With the venv active:

```bash
python3 -m unittest discover -s tests -v   # no MIDI hardware needed
python3 tools/monitor.py                   # live decode of everything the mixer sends
python3 tools/osc_dump.py --port 4003      # print what the bridge sends over OSC
```

`tools/monitor.py` shares `main.py`'s masks, so it cannot drift from the bridge. Unknown
messages are highlighted — that is how the aux, bus and solo support above was found.
