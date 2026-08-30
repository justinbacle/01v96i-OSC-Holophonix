"""MIDI port listing and selection."""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

import mido

from yamaha01v96i import encoder, events, protocol
from yamaha01v96i import parse


def input_names() -> List[str]:
    return list(mido.get_input_names())  # pyright: ignore[reportAttributeAccessIssue]


def console_ports() -> List[str]:
    """Input ports that look like an 01V96i, by name."""
    return [p for p in input_names() if "01V96i" in p]


def output_names() -> List[str]:
    return list(mido.get_output_names())  # pyright: ignore[reportAttributeAccessIssue]


def _resolve(names: List[str], wanted: Optional[str]) -> Optional[str]:
    if not wanted:
        return None
    matches = [n for n in names if wanted.lower() in n.lower()]
    if not matches:
        raise SystemExit(f"No MIDI port matching {wanted!r}.\nAvailable:\n  " + "\n  ".join(names))
    return matches[0]


def resolve_input(wanted: Optional[str]) -> Optional[str]:
    """Resolve an input port by substring, e.g. "MIDI 5" for the console's Tx PORT."""
    return _resolve(input_names(), wanted)


def resolve_output(wanted: Optional[str]) -> Optional[str]:
    """Resolve an output port by substring, e.g. "MIDI 4" for the console's Rx PORT."""
    return _resolve(output_names(), wanted)


def select_interactively() -> Optional[str]:
    """Prompt for a port. Returns None if there are none or the user gives up."""
    ports = input_names()
    if not ports:
        logging.error("No MIDI input ports found.")
        return None
    print("Available MIDI input ports:")
    for idx, port in enumerate(ports):
        marker = "  <- 01V96i" if "01V96i" in port else ""
        print(f"  [{idx}] {port}{marker}")
    while True:
        try:
            selection = int(input("Select MIDI port number: "))
            if 0 <= selection < len(ports):
                return ports[selection]
        except (ValueError, IndexError):
            pass
        except (EOFError, KeyboardInterrupt):
            return None
        print("Invalid selection. Please try again.")


def detect_console(timeout: float = 0.25) -> Tuple[Optional[str], Optional[str]]:
    """Find the console's working (input, output) pair by probing.

    Sends a harmless parameter *request* on each candidate output and watches every
    candidate input for the reply. Whichever pair answers is the one to use, whatever
    the console's Rx/Tx PORT and Studio Manager assignments happen to be -- which is
    what makes this robust where "pick the first port" is not.

    Falls back to the port emitting the keepalive, then to the first console input.
    """
    inputs, outputs = console_ports(), console_outputs()
    if not inputs:
        return None, None

    probe = mido.Message("sysex", data=encoder.request_channel_fader(0))
    open_inputs = [(name, mido.open_input(name)) for name in inputs]  # pyright: ignore
    try:
        for out_name in outputs:
            for _, port in open_inputs:
                while port.poll():
                    pass
            with mido.open_output(out_name) as out:  # pyright: ignore
                out.send(probe)
                deadline = time.time() + timeout
                while time.time() < deadline:
                    for in_name, port in open_inputs:
                        msg = port.poll()
                        if msg is None or msg.type != "sysex":
                            continue
                        if isinstance(parse(list(msg.bytes())[1:-1]), events.FaderMoved):
                            logging.info(f"Console detected: in={in_name} out={out_name}")
                            return in_name, out_name
                    time.sleep(0.002)

        # No reply: fall back to whichever input is at least emitting the keepalive.
        deadline = time.time() + timeout
        while time.time() < deadline:
            for in_name, port in open_inputs:
                msg = port.poll()
                if msg is not None and msg.type == "sysex" \
                        and looks_like_keepalive(list(msg.bytes())[1:-1]):
                    logging.info(f"Console input detected by keepalive: {in_name}")
                    return in_name, None
            time.sleep(0.002)
    finally:
        for _, port in open_inputs:
            port.close()

    logging.warning("Console did not answer a probe; falling back to the first port.")
    return inputs[0], (outputs[0] if outputs else None)


def console_outputs() -> List[str]:
    """Output ports that look like an 01V96i, by name."""
    return [p for p in output_names() if "01V96i" in p]


def looks_like_keepalive(data: List[int]) -> bool:
    """The console emits this ~6x/second, which identifies the right port.

    Note it arrives on MIDI 1 only, which is also the port carrying everything
    else -- the configured Tx Port carries a subset (docs/01v96i.md §0).
    """
    return tuple(data) == protocol.KEEPALIVE
