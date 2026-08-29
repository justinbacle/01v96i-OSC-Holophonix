"""Holophonix backend: 01V96i events -> Holophonix OSC addresses.

The only place Holophonix address strings and its value conventions live.
Controls the console sends but Holophonix has no mapping for yet (aux, bus, solo,
the EQ filter enable) are logged rather than silently dropped.
"""
from __future__ import annotations

import logging
import math
from typing import Dict

from yamaha01v96i import events as ev

# Surround X/Y arrive as -1..1; Holophonix distance is in the same units as this
# scale, so the pair is converted to polar after scaling.
XY_SCALE = 10


class HolophonixBackend:
    def __init__(self, osc_sender) -> None:
        self.osc_sender = osc_sender
        self._x: Dict[int, float] = {}
        self._y: Dict[int, float] = {}

    # --- helpers ------------------------------------------------------------ #

    def _send(self, address: str, value, fmt: str = "") -> None:
        self.osc_sender.send(address, value)
        shown = format(value, fmt) if fmt else value
        logging.debug(f"OSC sent: {address} {shown}")

    @staticmethod
    def _track(channel: int) -> str:
        return f"/track/{channel + 1}"

    def _eq_address(self, event: ev.EqChanged, leaf: str) -> str:
        base = "/master" if event.selector == "master" else self._track(event.channel)
        return f"{base}/equalizer/filter/{event.band}/{leaf}"

    # --- event handling ----------------------------------------------------- #

    def handle(self, event: ev.MixerEvent) -> None:
        handler = self._HANDLERS.get(type(event))
        if handler is not None:
            handler(self, event)

    def _on_fader(self, e: ev.FaderMoved) -> None:
        self._send(f"{self._track(e.channel)}/gain", e.db, ".1f")

    def _on_master_fader(self, e: ev.MasterFaderMoved) -> None:
        self._send("/master/gain", e.db, ".1f")

    def _on_mute(self, e: ev.MuteChanged) -> None:
        # Holophonix takes 1 = muted, the inverse of the console's ON semantics.
        self._send(f"{self._track(e.channel)}/mute", int(e.muted))

    def _on_master_mute(self, e: ev.MasterMuteChanged) -> None:
        self._send("/master/mute", int(e.muted))

    def _on_pan(self, e: ev.PanMoved) -> None:
        self._send(f"{self._track(e.channel)}/azim", e.value * 45, ".1f")

    def _on_surround(self, e: ev.SurroundMoved) -> None:
        table = self._x if e.axis == "x" else self._y
        table[e.channel] = e.value * XY_SCALE
        x = self._x.get(e.channel, 0.0)
        y = self._y.get(e.channel, 0.0)
        azim = math.degrees(math.atan2(x, y))
        dist = (x ** 2 + y ** 2) ** 0.5
        self._send(f"{self._track(e.channel)}/azim", azim, ".1f")
        self._send(f"{self._track(e.channel)}/dist", dist, ".3f")

    def _on_eq(self, e: ev.EqChanged) -> None:
        if e.gain_db is not None:
            self._send(self._eq_address(e, "gain"), e.gain_db)
        elif e.freq_hz is not None:
            self._send(self._eq_address(e, "freq"), e.freq_hz)
        elif e.q is not None:
            self._send(self._eq_address(e, "q"), e.q)
        elif e.filter_type is not None:
            logging.debug(f"EQ filter type: {e.selector} channel={e.channel} "
                          f"band={e.band} {e.filter_type}")
        elif e.enabled is not None:
            # TODO: unmapped -- which Holophonix filter slot this belongs to is the
            # open question in docs/01v96i.md §5.2.
            logging.info(f"EQ filter enable: {e.selector} channel={e.channel} "
                         f"band={e.band} enabled={e.enabled}")

    # Decoded but unmapped: logged so nothing is silently lost.
    def _on_aux_send(self, e: ev.AuxSendMoved) -> None:
        logging.info(f"Aux send: aux={e.aux} channel={e.channel + 1} {e.db:+.1f} dB")

    def _on_aux_master(self, e: ev.AuxMasterMoved) -> None:
        logging.info(f"Aux master: aux={e.aux} {e.db:+.1f} dB")

    def _on_bus_fader(self, e: ev.BusFaderMoved) -> None:
        logging.info(f"Bus fader: bus={e.bus} {e.db:+.1f} dB")

    def _on_bus_on(self, e: ev.BusOnChanged) -> None:
        logging.info(f"Bus ON: bus={e.bus} on={e.on}")

    def _on_aux_on(self, e: ev.AuxOnChanged) -> None:
        logging.info(f"Aux ON: aux={e.aux} on={e.on}")

    def _on_solo(self, e: ev.SoloChanged) -> None:
        logging.info(f"Solo: channel={e.channel + 1} soloed={e.soloed}")

    def _on_status(self, e: ev.ConsoleStatus) -> None:
        logging.debug(f"Console status: {e.kind} param={e.param} value={e.value}")

    _HANDLERS = {
        ev.FaderMoved: _on_fader,
        ev.MasterFaderMoved: _on_master_fader,
        ev.MuteChanged: _on_mute,
        ev.MasterMuteChanged: _on_master_mute,
        ev.PanMoved: _on_pan,
        ev.SurroundMoved: _on_surround,
        ev.EqChanged: _on_eq,
        ev.AuxSendMoved: _on_aux_send,
        ev.AuxMasterMoved: _on_aux_master,
        ev.BusFaderMoved: _on_bus_fader,
        ev.BusOnChanged: _on_bus_on,
        ev.AuxOnChanged: _on_aux_on,
        ev.SoloChanged: _on_solo,
        ev.ConsoleStatus: _on_status,
        ev.Keepalive: lambda self, e: None,
    }
