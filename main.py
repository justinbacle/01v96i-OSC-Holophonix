"""Yamaha 01V96i -> OSC bridge.

Wiring only: pick a MIDI port, decode with `yamaha01v96i`, hand the events to a
backend. Protocol knowledge lives in `yamaha01v96i/`, address schemes in
`backends/`.
"""
from __future__ import annotations

import argparse
import logging
import threading
import time

from backends.holophonix import HolophonixBackend
from backends.reaper import ReaperBackend
import mido

from midi import ports
from midi.midi_sysex import MidiSysexListener
from backends.reaper_inbound import ReaperInbound
from osc.osc_receiver import OSCReceiver
from osc.osc_sender import OSCSender
from yamaha01v96i import encoder, parse


BACKENDS = {"holophonix": HolophonixBackend, "reaper": ReaperBackend}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yamaha 01v96i MIDI to OSC bridge")
    parser.add_argument("--ip", default="192.168.1.104", help="OSC destination IP")
    parser.add_argument("--port", type=int, default=4003, help="OSC destination port")
    parser.add_argument("--midi-in", help="MIDI input port: the console's Tx PORT "
                                          "(substring match; skips the prompt)")
    parser.add_argument("--midi-out", help="MIDI output port: the console's Rx PORT "
                                           "(substring match; enables sending)")
    parser.add_argument("--backend", choices=sorted(BACKENDS), default="holophonix",
                        help="which OSC address scheme to emit")
    parser.add_argument("--listen-port", type=int,
                        help="UDP port to receive OSC feedback on, so the DAW can drive "
                             "the console (reaper backend only)")
    parser.add_argument("--no-sync", dest="sync", action="store_false",
                        help="do not ask the console for its state on startup")
    parser.add_argument("-v", "--verbose", action="store_true", help="log every OSC send")
    return parser


# Requests are answered immediately, so a whole burst overruns the input buffer
# while nothing is draining it: sending all 805 at once loses about 60% of the
# replies. Chunks of 64 with a short pause let the listener keep up and every
# reply arrives, in roughly a third of a second.
SYNC_CHUNK = 64
SYNC_PAUSE_S = 0.02
SYNC_STARTUP_DELAY_S = 0.3


def request_state(outport) -> None:
    """Ask the console for everything, paced so no replies are dropped.

    Runs after the listener is up: the replies are ordinary parameter changes, so
    they arrive through the normal decode path and populate the backend with no
    special casing.
    """
    time.sleep(SYNC_STARTUP_DELAY_S)  # let the listener come up first
    requests = encoder.state_requests()
    logging.info(f"Requesting console state ({len(requests)} parameters)...")
    for start in range(0, len(requests), SYNC_CHUNK):
        for payload in requests[start:start + SYNC_CHUNK]:
            outport.send(mido.Message("sysex", data=payload))
        time.sleep(SYNC_PAUSE_S)


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s: %(message)s")

    sender = OSCSender(args.ip, args.port)
    inbound: ReaperInbound | None = None

    class EchoAwareSender:
        """Passes sends through, recording them so REAPER's echo can be ignored."""

        def send(self, address: str, *values) -> None:
            if inbound is not None and values:
                inbound.note_sent(address, values[0])
            sender.send(address, *values)

    backend = BACKENDS[args.backend](EchoAwareSender())

    midi_port = ports.resolve_input(args.midi_in)
    midi_out = ports.resolve_output(args.midi_out)
    if not midi_port or not midi_out:
        # Probing finds the working pair whatever the console's port assignments are.
        detected_in, detected_out = ports.detect_console()
        midi_port = midi_port or detected_in
        midi_out = midi_out or detected_out
    if not midi_port:
        midi_port = ports.select_interactively()
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

    outport = None
    if midi_out:
        outport = mido.open_output(midi_out)  # pyright: ignore[reportAttributeAccessIssue]
        logging.info(f"Sending to {midi_out}")
    elif args.sync:
        logging.warning("No MIDI output found: starting without console state.")

    receiver = None
    if args.listen_port is not None:
        if outport is None:
            logging.error("--listen-port needs a MIDI output to drive the console")
            return 1
        if args.backend != "reaper":
            logging.error("--listen-port is only implemented for the reaper backend")
            return 1
        inbound = ReaperInbound(outport)
        receiver = OSCReceiver("0.0.0.0", args.listen_port, inbound.handle)
        receiver.start()

    if args.sync and outport is not None:
        threading.Thread(target=request_state, args=(outport,), daemon=True).start()

    def check_exit() -> None:
        while True:
            try:
                if input().strip().lower() == "q":
                    break
            except EOFError:
                # No console attached (service, nohup, redirected stdin): there is
                # no one to type 'q', so stop watching rather than stopping the bridge.
                return
            except KeyboardInterrupt:
                break
        listener.stop()
        logging.info("Exiting Sysex listener...")

    threading.Thread(target=check_exit, daemon=True).start()
    logging.info(f"Listening for Sysex on {midi_port}... (press 'q' + Enter to exit)")
    listener.listen()
    if receiver is not None:
        receiver.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
