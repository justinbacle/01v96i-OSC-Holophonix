# EQ Implementation Notes

## Band mapping: 01v96i → Holophonix

The 01v96i has 4 EQ bands per channel, but their meaning differs from Holophonix's filter numbering.
Band 1 and Band 4 on the mixer are variable-type filters, so the target Holophonix band
depends on the filter type currently selected.

| 01v96i band | Filter type | Holophonix band |
| --- | --- | --- |
| Band 1 | HPF (cut) | 1 |
| Band 1 | Shelf | 2 |
| Band 1 | Bell | 3 |
| Band 2 | (fixed) | 4 |
| Band 3 | (fixed) | 5 |
| Band 4 | Bell | 6 |
| Band 4 | Shelf | 7 |
| Band 4 | LPF (cut) | 8 |

## SysEx structure

```text
[67, 16, 62, 127, 1, Sel, Param, Ch, ?, ?, u, v]
```

| Byte | Values | Meaning |
| --- | --- | --- |
| `data[5]` (Sel) | `82` = Master, `32` = Channel | Which bus |
| `data[6]` (Param) | `3` = Gain, `2` = Freq, `1` = Type/Q | Which parameter |
| `data[7]` (Ch) | `0`–`15` | Channel number (if Sel = 32) |
| `data[10]` (u) | `0`–`127` | High byte of value |
| `data[11]` (v) | `0`–`127` | Low byte of value |

**Note:** for Master (Sel = 82), `data[7]` is `0` or `1` for L/R — not a channel number.

Band selection (which mixer band a message belongs to) still needs to be confirmed on hardware —
the SysEx byte that distinguishes Band 1 / 2 / 3 / 4 is not yet identified (`TODO` in code).

## Current state (`eq_band_1_handler`)

- **Gain** (`data[6] == 3`): working. 14-bit signed value scaled to ±18 dB.
  Always sends to Holophonix band 1 regardless of filter type — needs fixing once
  band routing is known.
- **Frequency** (`data[6] == 2`): working. Log interpolation from raw value (5–124)
  to Hz (21.2–20 000). Same band-routing caveat as gain.
- **Type/Q** (`data[6] == 1`): partially working.
  - Filter type is decoded from `data[11]`: `44` = HPF, `41` = Shelf, anything else = Bell.
  - `_bandType` is assigned but **never used** — the band routing is not wired up yet.
  - Q is only computed and sent for Bell filters (log scaling: raw 0–40 → Q 10–0.1).
  - HPF and Shelf cases need Q handling verified on hardware (may not apply or use
    a different formula).

## What needs doing

1. **Identify the SysEx byte that encodes band number** (Band 1 / 2 / 3 / 4).
   Requires capturing SysEx while switching between bands on the mixer.
   Current mask accepts any value for bytes 8 and 9 — one of these is likely the band index.

2. **Wire up band routing**: once filter type is decoded (`data[6] == 1`), use the table
   above to determine the target Holophonix band, then re-send the previously received
   gain and frequency to the correct band.
   This implies keeping per-channel, per-band state (last gain, last freq) so they can
   be re-routed when the filter type changes.

3. **Add handlers for Bands 2, 3, 4** once their SysEx byte pattern is known.
   Bands 2 and 3 are fixed-type (no routing needed), so they only need gain and frequency.
   Band 4 follows the same variable-type logic as Band 1.

4. **Verify HPF/Shelf Q behaviour** on hardware — check whether the mixer sends a Q value
   for these filter types or whether Q is fixed/irrelevant.
