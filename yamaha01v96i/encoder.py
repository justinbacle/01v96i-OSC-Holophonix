"""Build 01V96i SysEx messages to send *to* the console.

The mirror of parser.py. Payloads exclude the F0/F7 framing, matching what the
parser consumes and what mido's ``Message("sysex", data=...)`` expects, so a
message can be round-tripped through parse() to check it before sending.

The console only acts on these if Parameter Change **Rx** is enabled in its MIDI
setup and its device number matches (Reference Manual §2.8.3.2).
"""
from __future__ import annotations

from typing import List

from . import parser as _parser
from . import protocol as p


def parameter_change(element: int, param: int, channel: int, value: int) -> List[int]:
    """A parameter change for the edit buffer: the console applies it immediately."""
    return [p.YAMAHA_ID, p.DEVICE_BYTE, p.GROUP_ID, p.MODEL_UNIVERSAL, p.ADDRESS_EDIT_BUFFER,
            element, param, channel] + p.encode_value(value)


def parameter_request(element: int, param: int, channel: int) -> List[int]:
    """Ask the console for a parameter's current value.

    Same message with SUB STATUS 3n instead of 1n and no data bytes; the console
    replies with the corresponding parameter change (Reference Manual §2.8.3.3).
    """
    return [p.YAMAHA_ID, p.REQUEST_DEVICE_BYTE, p.GROUP_ID, p.MODEL_UNIVERSAL,
            p.ADDRESS_EDIT_BUFFER, element, param, channel]


def channel_fader(channel: int, raw: int) -> List[int]:
    """Set a channel fader by position index (0..1023). See protocol.fader_raw()."""
    return parameter_change(_parser.EL_CH_FADER, 0, channel, raw)


def channel_fader_db(channel: int, db: float) -> List[int]:
    """Set a channel fader to a dB value, via the measured fader law."""
    return channel_fader(channel, p.fader_raw(db))


def channel_on(channel: int, on: bool) -> List[int]:
    """Set a channel's ON state (True = unmuted, matching the console)."""
    return parameter_change(_parser.EL_CH_ON, 0, channel, int(on))


def master_fader(raw: int) -> List[int]:
    """Set the stereo fader by position index; slot 0 is the L of the linked pair."""
    return parameter_change(_parser.EL_MASTER_FADER, 0, 0, raw)


def request_channel_fader(channel: int) -> List[int]:
    return parameter_request(_parser.EL_CH_FADER, 0, channel)
