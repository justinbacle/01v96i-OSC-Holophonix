"""MIDI port listing and selection."""
from __future__ import annotations

import logging
from typing import List, Optional

import mido

from yamaha01v96i import protocol


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


def looks_like_keepalive(data: List[int]) -> bool:
    """The console emits this ~6x/second, which identifies the right port.

    Note it arrives on MIDI 1 only, which is also the port carrying everything
    else -- the configured Tx Port carries a subset (docs/01v96i.md §0).
    """
    return tuple(data) == protocol.KEEPALIVE
