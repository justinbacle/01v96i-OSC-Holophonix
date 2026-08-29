#!/usr/bin/env python3
"""Capture and log 01V96i MIDI traffic for protocol discovery.

Standalone companion to ``main.py`` — receives MIDI, sends no OSC. Every SysEx
message is printed to the terminal and appended to a JSONL log file. Messages
that match the known masks in ``main.py`` are annotated with their control
name; anything else is flagged ``*** UNKNOWN ***`` (those are the interesting
ones — see docs/01v96i.md §9 and docs/device-validation.md).

Usage:
    python3 tools/capture.py                       # interactive port selection
    python3 tools/capture.py --port "01V96i"       # explicit port name
    python3 tools/capture.py --out session1.jsonl  # explicit log file
    python3 tools/capture.py --all                 # also log non-SysEx messages
    python3 tools/capture.py --unknown-only         # console shows UNKNOWN only

Log format (one JSON object per line):
    {"ts": "2026-05-18T...", "type": "sysex", "hex": "F0 43 10 ... F7",
     "dec": [67, 16, ...], "known": "channel_fader"}

Run from the repository root (the script fixes up ``sys.path`` itself).
Requires the project environment (mido, python-osc) — see README § Setup.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import mido
except ImportError:  # pragma: no cover
    print("mido is required: see README § Setup (venv + requirements.txt)", file=sys.stderr)
    sys.exit(1)

# Reuse the masks from main.py so this tool can never drift from the bridge.
# (After the refactor, import from yamaha01v96i instead — see docs/refactor-plan.md.)
from main import SysexHandler  # noqa: E402

# Same order as the dispatcher registration in main.main() — first match wins.
KNOWN_MESSAGES: List[tuple] = [
    ("ignore", SysexHandler.ignore_specific_message_mask),
    ("master_fader", SysexHandler.master_fader_mask),
    ("master_mute_form_a", SysexHandler.master_mute_mask_1),
    ("master_mute_form_b", SysexHandler.master_mute_mask_2),
    ("channel_fader", SysexHandler.channel_fader_mask),
    ("channel_mute_form_a", SysexHandler.mute_mask_1),
    ("channel_mute_form_b", SysexHandler.mute_mask_2),
    ("aux_send", SysexHandler.aux_send_mask),
    ("aux_master", SysexHandler.aux_master_mask),
    ("bus_fader", SysexHandler.bus_fader_mask),
    ("bus_on", SysexHandler.bus_on_mask),
    ("aux_on", SysexHandler.aux_on_mask),
    ("pan", SysexHandler.pan_mask),
    ("surround_y", SysexHandler.y_mask),
    ("surround_x", SysexHandler.x_mask),
    ("eq", SysexHandler.eq_mask),
]


def annotate(data: List[int]) -> Optional[str]:
    """Return the control name for a known SysEx payload, else None."""
    for name, mask_fn in KNOWN_MESSAGES:
        try:
            if mask_fn(list(data)):
                return name
        except Exception:  # masks should be total, but never crash the capture
            continue
    return None


def format_hex(data: List[int]) -> str:
    """Format a SysEx payload with its F0/F7 framing for readability."""
    return "F0 " + " ".join(f"{b:02X}" for b in data) + " F7"


def run_capture(
    inport: Iterable,
    out_path: Path | str,
    *,
    log_all: bool = False,
    unknown_only: bool = False,
) -> Counter:
    """Consume messages from a mido input, logging each one to ``out_path``.

    ``inport`` is any iterable of mido messages — a real ``mido.open_input``
    port or a test double (see tests/test_capture_tool.py). Stops on Ctrl-C or
    when the iterable is exhausted; returns a Counter of annotations
    (``UNKNOWN`` for unmatched SysEx, ``other:<type>`` for non-SysEx messages).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    total = 0

    try:
        with out_path.open("a", encoding="utf-8") as log:
            for msg in inport:
                ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

                if msg.type == "sysex":
                    data = list(msg.data)
                    known = annotate(data)
                    entry = {
                        "ts": ts,
                        "type": "sysex",
                        "hex": format_hex(data),
                        "dec": data,
                        "known": known,
                    }
                    counts[known if known else "UNKNOWN"] += 1
                    total += 1
                    if not (unknown_only and known):
                        print(f"{ts}  {format_hex(data):40s}  {known or '*** UNKNOWN ***'}")
                elif log_all:
                    entry = {"ts": ts, "type": msg.type, "data": msg.dict()}
                    counts[f"other:{msg.type}"] += 1
                    total += 1
                    print(f"{ts}  {msg}")
                else:
                    continue

                log.write(json.dumps(entry) + "\n")
                log.flush()
    except KeyboardInterrupt:
        print()

    print(f"{total} messages captured -> {out_path}")
    for name, count in counts.most_common():
        print(f"  {name}: {count}")
    return counts


def open_port(name: Optional[str]):
    """Open a MIDI input port by name, or interactively if no name given."""
    if name is not None:
        try:
            return mido.open_input(name)  # pyright: ignore[reportAttributeAccessIssue]
        except Exception:
            print(f"MIDI input port not found: {name!r}", file=sys.stderr)
            print("Available ports:", file=sys.stderr)
            for p in mido.get_input_names():  # pyright: ignore[reportAttributeAccessIssue]
                print(f"  - {p}", file=sys.stderr)
            sys.exit(1)

    try:
        ports = mido.get_input_names()  # pyright: ignore[reportAttributeAccessIssue]
    except Exception as exc:
        print(f"No usable MIDI backend available ({exc}).", file=sys.stderr)
        print("Install python-rtmidi (see requirements.txt / README § Setup).", file=sys.stderr)
        sys.exit(1)

    if not ports:
        print("No MIDI input ports found.", file=sys.stderr)
        sys.exit(1)

    print("Available MIDI input ports:")
    for idx, port in enumerate(ports):
        print(f"  [{idx}] {port}")
    while True:
        try:
            selection = int(input("Select MIDI port number: "))
            if 0 <= selection < len(ports):
                return mido.open_input(ports[selection])  # pyright: ignore[reportAttributeAccessIssue]
        except (ValueError, IndexError):
            pass
        print("Invalid selection. Please try again.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture 01V96i MIDI SysEx traffic with known-message annotation."
    )
    parser.add_argument("--port", help="MIDI input port name (skips interactive selection)")
    parser.add_argument(
        "--out",
        default=None,
        help="JSONL output file (default: captures/capture_<timestamp>.jsonl)",
    )
    parser.add_argument(
        "--all", action="store_true", help="also log non-SysEx messages (CC, notes, ...)"
    )
    parser.add_argument(
        "--unknown-only",
        action="store_true",
        help="console shows UNKNOWN messages only (file still records everything)",
    )
    args = parser.parse_args()

    out_path = (
        Path(args.out)
        if args.out
        else REPO_ROOT
        / "captures"
        / f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )

    inport = open_port(args.port)
    print(f"Listening on {inport.name} — Ctrl-C to stop")
    print(f"Logging to {out_path}")
    if args.unknown_only:
        print("(console filtered to UNKNOWN messages)")

    try:
        run_capture(inport, out_path, log_all=args.all, unknown_only=args.unknown_only)
    finally:
        inport.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())