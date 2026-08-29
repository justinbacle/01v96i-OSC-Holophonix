"""Yamaha 01V96i -> OSC bridge.

Wiring only: pick a MIDI port, decode with `yamaha01v96i`, hand the events to a
backend. Protocol knowledge lives in `yamaha01v96i/`, address schemes in
`backends/`.
"""
from __future__ import annotations

import argparse
import logging
import threading

from backends.holophonix import HolophonixBackend
from midi import ports
from midi.midi_sysex import MidiSysexListener
from osc.osc_sender import OSCSender
from yamaha01v96i import parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yamaha 01v96i MIDI to OSC bridge")
    parser.add_argument("--ip", default="192.168.1.104", help="OSC destination IP")
    parser.add_argument("--port", type=int, default=4003, help="OSC destination port")
    parser.add_argument("--midi-port", help="MIDI input port name (skips the prompt)")
    parser.add_argument("-v", "--verbose", action="store_true", help="log every OSC send")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")

    backend = HolophonixBackend(OSCSender(args.ip, args.port))

    midi_port = args.midi_port or ports.select_interactively()
    if not midi_port:
        return 1

    def on_sysex(data) -> None:
        payload = list(data)
        event = parse(payload)
        if event is None:
            logging.warning(f"Unhandled Sysex: {payload}")
            return
        backend.handle(event)

    listener = MidiSysexListener(midi_port)
    listener.add_callback(on_sysex)

    def check_exit() -> None:
        while True:
            try:
                if input().strip().lower() == "q":
                    break
            except (EOFError, KeyboardInterrupt):
                break
        listener.stop()
        logging.info("Exiting Sysex listener...")

    threading.Thread(target=check_exit, daemon=True).start()
    logging.info(f"Listening for Sysex on {midi_port}... (press 'q' + Enter to exit)")
    listener.listen()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
