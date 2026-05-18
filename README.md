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

```bash
pip install -r requirements.txt
python3 main.py
```

On startup you will be prompted to select a MIDI input port. Type `q` + Enter to quit.

**OSC destination** is currently hardcoded at `192.168.1.104:4003` in `main.py`.

## OSC address mapping

| Mixer control | OSC address | Value range |
| --- | --- | --- |
| Channel fader | `/track/{n}/gain` | −60 to +12 dB |
| Channel mute | `/track/{n}/mute` | 0 / 1 |
| Channel pan | `/track/{n}/azim` | −45 to +45° |
| Surround X/Y | `/track/{n}/azim` + `/track/{n}/dist` | polar coords |
| Master fader | `/master/gain` | −60 to +12 dB |
| Master mute | `/master/mute` | 0 / 1 |
| EQ gain | `/track/{n}/equalizer/filter/{b}/gain` | −18 to +18 dB |
| EQ frequency | `/track/{n}/equalizer/filter/{b}/freq` | 21.2 Hz – 20 kHz |
| EQ Q | `/track/{n}/equalizer/filter/{b}/q` | — |

`n` = track number (1-based), `b` = EQ band index.

---

## Implementation status

### Done

- **Channel faders** — all 16 channels; 14-bit MIDI value → dB
- **Master fader** — same scaling as channel faders
- **Channel mute** — two SysEx variants (different mixer modes)
- **Master mute** — two SysEx variants
- **Pan (L/R)** — maps to ±45° azimuth
- **Surround X/Y** — converts mixer surround pan X/Y parameters to azimuth + distance (polar)
- **MIDI port selection** — interactive on startup
- **OSC transport** — UDP via `python-osc`

### Partial / in progress

- **EQ Band 1** — gain and frequency are working; Q-factor only handled for Bell filter type;
  HPF/Shelf/Bell band-type routing is documented but not fully wired
- **EQ band mapping** — the intended mapping (HPF → band 1, Shelf → band 2, Bell → band 3)
  is commented in the code but not yet enforced

### Not yet implemented

- **ADM-OSC position mode** — alternative output mode using the
  [ADM-OSC](https://github.com/immersive-audio-live/ADM-OSC) open standard instead of the
  proprietary Holophonix addresses. Requires:
  - Cartesian output: `/adm/obj/{n}/x`, `/adm/obj/{n}/y` (range −1 to 1) from mixer surround X/Y
  - Polar output: `/adm/obj/{n}/azim`, `/adm/obj/{n}/dist` (azimuth −180 to 180°, distance 0 to 1)
  - Gain: `/adm/obj/{n}/gain` (linear 0–1) instead of dB
  - A runtime mode switch (Holophonix vs ADM-OSC) so both targets can be supported
- **EQ Bands 2, 3, 4** — no handlers registered
- **Configuration file** — OSC host/port are hardcoded
- **Other mixer parameters** — compressor, gates, reverb sends, aux routing, etc. (scope TBD)
- **Bidirectional sync** — no state received from Holophonix; mixer position is not updated on connect

## Project structure

```text
main.py                  # Application entry point; all MIDI→OSC logic
osc/osc_sender.py        # Thin UDP wrapper around python-osc
midi/midi_sysex.py       # MIDI SysEx listener class (defined, not yet used)
requirements.txt
```
