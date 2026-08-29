#!/usr/bin/env python3
"""Minimal OSC receiver that prints everything it receives.

Use as a stand-in OSC target when validating the bridge without a real
Holophonix unit:

    # terminal 1
    python3 tools/osc_dump.py --port 4003

    # terminal 2: point main.py at this machine (OSC_IP in main(), e.g. 127.0.0.1)
    python3 main.py

Every received message is printed with a UTC timestamp:
    2026-05-18T...  /track/3/gain  (-14.041035056691467,)

Requires the project environment (python-osc) — see README § Setup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer


def _print_message(address: str, *args) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    print(f"{ts}  {address}  {args}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print every OSC message received on a UDP port."
    )
    parser.add_argument("--host", default="0.0.0.0", help="bind address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=4003, help="UDP port (default 4003)")
    args = parser.parse_args()

    dispatcher = Dispatcher()
    dispatcher.set_default_handler(_print_message)
    server = BlockingOSCUDPServer((args.host, args.port), dispatcher)
    print(f"Listening for OSC on {args.host}:{args.port} (Ctrl-C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
