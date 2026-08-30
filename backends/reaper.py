"""REAPER backend: 01V96i events -> REAPER's OSC addresses.

Addresses and value conventions come from REAPER's own definition file, shipped
at Plugins/Default.ReaperOSC, rather than from guesswork:

    TRACK_VOLUME  f/track/@/volume/db     real dB
    TRACK_PAN     n/track/@/pan           normalized, 0 = hard left .. 1 = hard right
    TRACK_MUTE    b/track/@/mute          boolean
    TRACK_SOLO    b/track/@/solo          boolean
    MASTER_VOLUME n/master/volume         normalized fader position

Note the console drives REAPER from its **normal mixing layer**, not the REMOTE
layer: the SysEx the bridge decodes is emitted while the console is a mixer. The
REMOTE layer is a mode that takes the console over (Reference Manual p. 83) and
speaks HUI on the DAW ports, which is a different protocol entirely.

REAPER setup: Preferences -> Control/OSC/web -> Add -> OSC, with the listen port
matching --port, then the console's channels map to REAPER tracks 1:1.
"""
from __future__ import annotations

import logging
from typing import Dict

from yamaha01v96i import events as ev
from yamaha01v96i import protocol

# TRACK_VOLUME accepts real dB (f/track/@/volume/db), which is what the console
# gives us, so tracks are exact. MASTER_VOLUME has only the normalized pattern
# (n/master/volume): REAPER's normalized scale is its own fader taper, not a dB
# scale, so the honest mapping is position to position -- the console's fader
# travel onto REAPER's. The tapers differ, so the master follows REAPER's fader
# position rather than matching dB for dB.


class ReaperBackend:
    """Maps console events onto REAPER tracks, one console channel per track."""

    def __init__(self, osc_sender) -> None:
        self.osc_sender = osc_sender

    def _send(self, address: str, value) -> None:
        self.osc_sender.send(address, value)
        logging.debug(f"OSC sent: {address} {value}")

    @staticmethod
    def _track(channel: int) -> str:
        return f"/track/{channel + 1}"

    def handle(self, event: ev.MixerEvent) -> None:
        handler = self._HANDLERS.get(type(event))
        if handler is not None:
            handler(self, event)

    def _on_fader(self, e: ev.FaderMoved) -> None:
        self._send(f"{self._track(e.channel)}/volume/db", e.db)

    def _on_mute(self, e: ev.MuteChanged) -> None:
        self._send(f"{self._track(e.channel)}/mute", 1 if e.muted else 0)

    def _on_solo(self, e: ev.SoloChanged) -> None:
        self._send(f"{self._track(e.channel)}/solo", 1 if e.soloed else 0)

    def _on_pan(self, e: ev.PanMoved) -> None:
        # Console -1..+1 -> REAPER's normalized 0..1, centre at 0.5.
        self._send(f"{self._track(e.channel)}/pan", (e.value + 1.0) / 2.0)

    def _on_master_fader(self, e: ev.MasterFaderMoved) -> None:
        raw = protocol.fader_raw(e.db, unity_top=True)
        self._send("/master/volume", raw / protocol.FADER_MAX_RAW)

    def _on_master_mute(self, e: ev.MasterMuteChanged) -> None:
        # REAPER has no master mute in the OSC definition; log rather than invent one.
        logging.info(f"Master mute {e.muted} has no REAPER OSC address; ignored")

    def _unmapped(self, e: ev.MixerEvent) -> None:
        logging.debug(f"No REAPER mapping for {type(e).__name__}")

    _HANDLERS: Dict[type, object] = {
        ev.FaderMoved: _on_fader,
        ev.MuteChanged: _on_mute,
        ev.SoloChanged: _on_solo,
        ev.PanMoved: _on_pan,
        ev.MasterFaderMoved: _on_master_fader,
        ev.MasterMuteChanged: _on_master_mute,
        # Decoded but deliberately not sent: REAPER's EQ is a plugin, addressed by
        # FX parameter index rather than by a console band, so mapping the 01V96i's
        # EQ onto it needs a decision about which plugin and which slot.
        ev.EqChanged: _unmapped,
        ev.EqOnChanged: _unmapped,
        ev.AttenuationChanged: _unmapped,
        ev.SurroundMoved: _unmapped,
        ev.AuxSendMoved: _unmapped,
        ev.AuxMasterMoved: _unmapped,
        ev.BusFaderMoved: _unmapped,
        ev.BusOnChanged: _unmapped,
        ev.AuxOnChanged: _unmapped,
        ev.ConsoleStatus: _unmapped,
        ev.Keepalive: _unmapped,
        ev.Ignored: _unmapped,
    }
