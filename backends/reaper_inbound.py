"""REAPER OSC feedback -> console SysEx.

The reverse of backends/reaper.py: REAPER sends the same patterns back as
feedback when something changes in the project, and this turns them into
parameter changes that move the console's motorised faders and lamps.

Echo suppression matters. Moving a console fader produces OSC out, REAPER echoes
the new value back, and applying that to the console would fight the operator's
hand. Any value the bridge itself just sent is therefore ignored for a short
window (see ECHO_WINDOW_S).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, Optional, Tuple

import mido

from yamaha01v96i import encoder, protocol

# How long a value the bridge sent is treated as our own echo coming back.
ECHO_WINDOW_S = 0.35

TRACK_VOLUME_DB = re.compile(r"^/track/(\d+)/volume/db$")
TRACK_MUTE = re.compile(r"^/track/(\d+)/mute$")
TRACK_SOLO = re.compile(r"^/track/(\d+)/solo$")
TRACK_PAN = re.compile(r"^/track/(\d+)/pan$")
MASTER_VOLUME = re.compile(r"^/master/volume$")


class ReaperInbound:
    """Applies REAPER's OSC feedback to the console."""

    def __init__(self, outport: "mido.ports.BaseOutput") -> None:
        self.outport = outport
        self._sent: Dict[str, Tuple[float, float]] = {}

    def note_sent(self, address: str, value: float) -> None:
        """Record a value the bridge sent, so REAPER's echo of it is ignored."""
        self._sent[address] = (float(value), time.time())

    def _is_echo(self, address: str, value: float, tolerance: float) -> bool:
        entry = self._sent.get(address)
        if entry is None:
            return False
        sent_value, sent_at = entry
        if time.time() - sent_at > ECHO_WINDOW_S:
            return False
        return abs(sent_value - float(value)) <= tolerance

    def handle(self, address: str, args: tuple) -> None:
        if not args:
            return
        value = args[0]
        payload = self._translate(address, value)
        if payload is None:
            return
        self.outport.send(mido.Message("sysex", data=payload))
        logging.debug(f"OSC in: {address} {value} -> console")

    def _translate(self, address: str, value) -> Optional[list]:
        match = TRACK_VOLUME_DB.match(address)
        if match:
            if self._is_echo(address, value, tolerance=0.2):
                return None
            return encoder.channel_fader_db(int(match.group(1)) - 1, float(value))

        match = TRACK_MUTE.match(address)
        if match:
            if self._is_echo(address, value, tolerance=0.01):
                return None
            # REAPER: 1 = muted. Console ON: 1 = unmuted.
            return encoder.channel_on(int(match.group(1)) - 1, not bool(round(float(value))))

        match = TRACK_SOLO.match(address)
        if match:
            if self._is_echo(address, value, tolerance=0.01):
                return None
            return encoder.solo(int(match.group(1)) - 1, bool(round(float(value))))

        match = TRACK_PAN.match(address)
        if match:
            if self._is_echo(address, value, tolerance=0.02):
                return None
            # REAPER normalized 0..1, centre 0.5 -> console -1..+1.
            return encoder.pan(int(match.group(1)) - 1, float(value) * 2.0 - 1.0)

        if MASTER_VOLUME.match(address):
            if self._is_echo(address, value, tolerance=0.01):
                return None
            raw = int(round(float(value) * protocol.FADER_MAX_RAW))
            return encoder.master_fader(raw)
        return None
