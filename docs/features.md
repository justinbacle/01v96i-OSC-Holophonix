# Feature inventory

What the console offers, what the bridge handles today, and what each intended use
needs. Sources: the Yamaha manuals in [docs/manuals/](manuals/), and on-device captures recorded in
[docs/01v96i.md](01v96i.md).

Status key: **done** decoded and encoded · **decoded** read but not sent anywhere ·
**none** not implemented.

## Per-channel parameters

Input channels 1–32, from the Reference Manual's channel signal flow:

| Parameter | Status | Notes |
| --- | --- | --- |
| Fader (LEVEL) | done | Position index 0–1023, measured dB law |
| ON / mute | done | Emitted in two forms; polarity confirmed |
| PAN | done | Console's own −63…+63 |
| ATT (attenuator) | decoded | Element `0x1D`, tenths of a dB, −96…+12 |
| 4-band EQ | done | Gain, freq, Q, filter type, per-band enable, whole-EQ bypass |
| Surround X / Y | done | Only present in surround mode |
| Solo | decoded | Setup address space |
| Aux send level | decoded | Element `0x23`, aux number in the parameter no. |
| **Phase** | none | Never captured |
| **GATE** | none | Dynamics; gate or ducking |
| **COMP** | none | Dynamics; compressor, expander or limiter |
| **INPUT DELAY** | none | Per-channel delay |
| **Insert** | none | |
| **Routing** (bus 1–8, stereo) | none | Which buses a channel feeds |
| **Aux send ON / pre-post** | none | We have the send *level* only |

ST IN channels 1–4 are a reduced set — phase, ATT, 4-band EQ, ON, LEVEL, PAN, aux
sends, meter — and carry no gate, comp or delay. All of what we support works on them,
with one caveat: **ST-IN pan is per-side**, L and R reading −63/+63, so neither slot is
"the channel's pan" (see [docs/01v96i.md](01v96i.md) § open questions).

## Outputs

| Target | Status | Notes |
| --- | --- | --- |
| Stereo (master) fader, ON, EQ | done | L/R slots linked; slot 0 acted on |
| Aux masters 1–8 fader, ON | decoded | |
| Aux EQ | decoded | Element `0x3C`, same layout as channel EQ |
| Bus 1–8 fader, ON | decoded | |
| Bus EQ | none | Hypothesised on the channel/aux/master pattern, never seen |
| Output attenuation, delay, insert | none | |

## Global

| Feature | Status | Notes |
| --- | --- | --- |
| Layer / selection indicators | decoded | Recognised, semantics unknown |
| EQ band selection | decoded | Which band the UI shows |
| Solo status | decoded | Global flags accompanying solo |
| **Scene recall / store** | none | Program Change, not SysEx — a different message class |
| **Fader / mute groups** | none | |
| **Effects processors 1–4** | none | |
| **Metering** | none | The remote-meter request exists in the protocol |

## What each use needs

### Holophonix spatial bridge — the current goal

Needs fader, mute, pan, surround X/Y and EQ. **All present.** What remains is not
protocol work but decisions: the OSC address scheme for the *decoded* rows above, the
filter-slot mapping in [docs/01v96i.md](01v96i.md) §5.2, and what a stereo input's pan
should mean. Plus one build task — the bridge can only *send* OSC, so Holophonix cannot
drive the console (see § Bidirectional below).

### DAW control — read this before building anything

The console already does this natively. Its **REMOTE layer** targets Pro Tools, Nuendo,
Cubase, "General DAW" (anything speaking the Pro Tools protocol) or User Defined, and is
selected with the LAYER `[REMOTE]` button. On that layer the faders and `[ON]` buttons
drive the external device directly, over the **DAW port pair** (USB 2–3 on this console).

Two consequences worth being clear about before committing to an MCU bridge:

1. **The protocol is not ours to invent.** Selecting "General DAW" makes the console
   speak the Pro Tools/HUI protocol on the DAW ports. An MCU bridge would *receive* that,
   not build it on top of SysEx. That is a different decoder from everything in
   `yamaha01v96i/`, though it could share the transport and tooling.
2. **It is a mode, not an addition.** The manual is explicit: during Remote operation
   "you cannot adjust the 01V96i's parameters unless you select a different layer". So
   the console is *either* a DAW surface *or* mixing — the SysEx bridge and a DAW surface
   cannot both be live on the same layer.

The **User Defined** remote target is the more flexible option: arbitrary MIDI messages
assigned to faders and `[ON]` buttons, in four recallable banks. That would let the
console emit whatever we choose without touching the Pro Tools protocol at all — worth
weighing against implementing HUI.

### General control surface

If the scope grows beyond spatial control, the gaps are the **none** rows above:
dynamics (gate, comp), delay, phase, routing, aux send ON and pre/post, and scene recall.
All are likely reachable the same way everything else was — move the control, read the
element and parameter number off the monitor, add a row to `MESSAGES`.

## Bidirectional

The console direction is complete: every parameter the bridge decodes it can also send,
and `--sync` reads the console's whole state on startup.

The OSC direction is not. `osc/osc_sender.py` can only send; nothing listens. So a level
change in Holophonix cannot move the console's motorised fader, even though the mechanism
to move it exists. Closing that needs an OSC server, a reverse mapping from Holophonix
addresses to `encoder` calls, and echo suppression so a console move does not bounce back
and fight the operator.
