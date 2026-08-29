#!/usr/bin/env python3
"""Send a channel fader value to the console.

The console applies the change and moves its motorised fader, but does NOT echo
parameter changes it receives -- it only reports moves made at the front panel.
So the absence of a reply here means nothing; watch the fader. Any reply that
does arrive is printed as a bonus.

Usage:
    python3 tools/send_fader.py --channel 1 --db 0
    python3 tools/send_fader.py --channel 1 --raw 823
    python3 tools/send_fader.py --channel 1 --sweep     # -inf, -30, -10, 0, +10

The console must have Parameter Change **Rx** enabled in its MIDI setup, with a
device number matching protocol.DEVICE_BYTE (Reference Manual §2.8.3.2).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import mido
except ImportError:  # pragma: no cover
    print("mido is required: see README § Setup", file=sys.stderr)
    sys.exit(1)

from yamaha01v96i import encoder, parse, protocol  # noqa: E402
from yamaha01v96i import events as ev  # noqa: E402


def pick_port(names: List[str], wanted: Optional[str]) -> str:
    match = [n for n in names if (wanted or "01V96i").lower() in n.lower()]
    if not match:
        raise SystemExit(f"No MIDI port matching {wanted or '01V96i'!r}.\n  "
                         + "\n  ".join(names))
    return match[0]


def send_and_verify(outport, inport, channel: int, raw: int, timeout: float = 1.5) -> bool:
    """Send one fader value; return True if the console reports it back."""
    payload = encoder.channel_fader(channel, raw)
    expected_db = protocol.fader_db(raw)
    print(f"  -> ch{channel + 1} raw {raw:4d} ({expected_db:+.1f} dB)   "
          f"{' '.join(f'{b:02X}' for b in payload)}")

    while inport.poll():  # drop anything already queued
        pass
    outport.send(mido.Message("sysex", data=payload))

    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = inport.poll()
        if msg is None:
            time.sleep(0.005)
            continue
        if msg.type != "sysex":
            continue
        event = parse(list(msg.bytes())[1:-1])
        if isinstance(event, ev.FaderMoved) and event.channel == channel:
            match = "OK" if abs(event.db - expected_db) < 0.05 else "MISMATCH"
            print(f"  <- console reports {event.db:+.1f} dB   [{match}]")
            return match == "OK"
    print("  <- no echo (expected: the console does not report changes it receives)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--channel", type=int, default=1, help="console channel, 1-based")
    ap.add_argument("--db", type=float, help="target level in dB")
    ap.add_argument("--raw", type=int, help="target position index, 0..1023")
    ap.add_argument("--sweep", action="store_true", help="step through several levels")
    ap.add_argument("--out-port", help="MIDI output port (default: first 01V96i)")
    ap.add_argument("--in-port", help="MIDI input port (default: first 01V96i)")
    args = ap.parse_args()

    out_name = pick_port(mido.get_output_names(), args.out_port)   # pyright: ignore
    in_name = pick_port(mido.get_input_names(), args.in_port)      # pyright: ignore
    print(f"out: {out_name}\nin:  {in_name}\n")

    if args.sweep:
        targets = [protocol.fader_raw(db) for db in (-90.0, -30.0, -10.0, 0.0, 10.0)]
    elif args.raw is not None:
        targets = [args.raw]
    elif args.db is not None:
        targets = [protocol.fader_raw(args.db)]
    else:
        targets = [protocol.fader_raw(0.0)]

    channel = args.channel - 1
    confirmed = 0
    with mido.open_output(out_name) as outport, mido.open_input(in_name) as inport:  # pyright: ignore
        for raw in targets:
            if send_and_verify(outport, inport, channel, raw):
                confirmed += 1
            time.sleep(0.4)

    print(f"\n{len(targets)} sent. Watch the fader -- that is the confirmation.")
    print("If nothing moved: check MIDI setup on the console -- Parameter Change Rx\n"
          "must be ON, and the device number must match (1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
