# Using the 01V96i as a REAPER control surface

The console controls REAPER and REAPER controls the console, over OSC, while the console
**stays a mixer**. It is not put into its REMOTE layer — see [Why not HUI](#why-not-hui).

```bash
./bridge
```

No arguments: it finds the console by probing, reads REAPER's OSC settings from REAPER's
own configuration, and reads the console's current state so both sides start in step.

## What is mapped

| Control | Console → REAPER | REAPER → Console |
| --- | --- | --- |
| Channel fader | yes, in real dB | yes |
| Channel mute | yes | yes |
| Solo | yes | yes |
| Pan | yes | yes |
| Master fader | yes | yes |
| Master mute | yes | **no** — REAPER does not expose it (see [Limits](#limits)) |
| EQ, aux sends, buses, ATT, surround | no | no |

Console channel *N* drives REAPER track *N*.

## Setting it up

### 1. Console

On the console (full detail in [docs/01v96i.md](01v96i.md) § Console configuration):

- `MIDI` → `[F1]`: **PARAMETER CHANGE Tx = ON** and **Rx = ON**, **ECHO = off**,
  **CHANNEL Tx/Rx = 1**
- `MIDI` → `[F1]`: **Fader Resolution = HIGH** — on LOW the faders drop to 256 steps and
  every dB value is silently wrong

### 2. REAPER — OSC surface

Preferences → **Control/OSC/web** → Add → **OSC (Open Sound Control)**:

| Field | Value | Why |
| --- | --- | --- |
| Mode | **Device IP/Port** | The receive-only mode makes REAPER *never send*, so the console would not follow REAPER at all |
| Device IP | `127.0.0.1` | |
| Device port | `9000` | Where REAPER sends; the bridge listens here |
| Pattern config | **`01V96i`** | A copy of REAPER's default with `DEVICE_TRACK_COUNT 32`, so more than 8 tracks are reachable |
| Allow binding messages to REAPER actions | ticked | Master mute is done through a REAPER action |

The pattern file lives at `~/.config/REAPER/OSC/01V96i.ReaperOSC`. Recreate it with:

```bash
sed 's/^DEVICE_TRACK_COUNT 8\r$/DEVICE_TRACK_COUNT 32\r/' \
    /opt/REAPER/Plugins/Default.ReaperOSC > ~/.config/REAPER/OSC/01V96i.ReaperOSC
```

(The `\r` matters — REAPER's file uses CRLF line endings.)

Device IP/Port mode has no configurable local port: REAPER binds an ephemeral one that
differs every launch. The bridge finds it in the system socket table, and falls back to
learning it from the first message REAPER sends.

### 3. Run

```bash
./bridge          # add -v to see every message
```

## Limits

- **Master mute is one-way.** `Default.ReaperOSC` has no `MASTER_MUTE` pattern. Muting
  REAPER's master emits only `/track/mute` for the *selected* track, which would mute the
  wrong console strip. Console → REAPER works through action 18, "Track: Set mute for
  master track (MIDI CC/OSC only)" — the *set* variant, so the two cannot drift apart.
- **Inserting a track shifts the mapping.** Console channel *N* follows REAPER track *N*,
  so inserting a track renumbers everything after it and the console follows. REAPER
  re-broadcasts the affected tracks, so the console's faders jump to the new values. This
  is how a positional surface behaves; there is no track-identity mapping.
- **Track window.** `DEVICE_TRACK_COUNT` limits how many tracks REAPER exposes. With
  REAPER's default of 8, tracks 9 and above are unreachable in both directions — which is
  what the `01V96i` pattern file above fixes.
- **The master fader is not a dB scale.** `MASTER_VOLUME` accepts only a normalized value
  on REAPER's own fader taper (0 dB ≈ 0.716, 1.0 = +12 dB). `REAPER_FADER_LAW` in
  `backends/reaper.py` was measured from REAPER itself; re-measure if REAPER's fader
  range preference changes.
- **EQ is not mapped.** ReaEQ is reachable — addressed by slot (`hipass`, `loshelf`,
  `band/@`, `hishelf`, `lopass`), which mirrors the console's own filter-type-picks-the-
  slot behaviour, and `DEVICE_EQ INSERT` inserts it automatically — but it is not
  implemented.

## Why not HUI

The console has a REMOTE layer that targets Pro Tools, Nuendo, Cubase or "General DAW",
speaking the **Pro Tools protocol (HUI)** over the DAW port pair. It is not MCU; the
manual never mentions Mackie or Logic Control. Three reasons it is not used here:

1. **It is a mode.** The Reference Manual (p. 83) states the console's own parameters
   cannot be adjusted while the REMOTE layer is active — so it is a DAW surface *or* a
   mixer, not both.
2. **HUI is the legacy protocol.** MCU superseded it, and REAPER's HUI support is partial.
3. **It crashes REAPER here.** Adding a HUI surface aborts inside ALSA's
   `snd_rawmidi_open`, called from `reaper_csurf.so` — `SIGABRT`, with coredumps.

The console does emit valid HUI on the DAW port when that layer is selected (confirmed:
zone/port select on CC `0x0F`/`0x2F`, 14-bit faders on CC `0x00`–`0x07` with LSB on
`0x20`–`0x27`), so the option remains open if transport control or scribble strips ever
matter enough to write a HUI decoder.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Console moves REAPER, REAPER does not move console | REAPER's OSC mode is receive-only; it never sends |
| Nothing moves at all | Check `PARAMETER CHANGE Tx/Rx` on the console; run `./bridge -v` and look for "Console detected" |
| Tracks above 8 do nothing | Pattern config is still `Default`; select `01V96i` |
| dB values look wrong | Console Fader Resolution is on LOW, not HIGH |
| Console faders jump unexpectedly | A track was inserted in REAPER; see Limits |
