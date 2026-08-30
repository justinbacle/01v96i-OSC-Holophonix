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
import os
import shlex
from pathlib import Path
from typing import Dict, NamedTuple, Optional

from yamaha01v96i import events as ev

# TRACK_VOLUME accepts real dB (f/track/@/volume/db), so tracks are exact.
# MASTER_VOLUME has only the normalized pattern (n/master/volume), and REAPER's
# normalized scale is its own fader taper -- 0 dB sits around 0.716, and 1.0 is
# +12 dB, so neither a linear dB map nor a straight position copy is right.
#
# This table was measured from REAPER itself: each normalized value was sent to a
# track fader and the dB REAPER reported back was recorded. Re-measure with
# captures/calibrate.py if REAPER's fader range preference changes.
REAPER_FADER_LAW = [
    (0.000, -150.00), (0.025, -90.14), (0.050, -72.08), (0.075, -61.51),
    (0.100, -54.01), (0.125, -48.19), (0.150, -43.43), (0.175, -39.39),
    (0.200, -35.89), (0.225, -32.79), (0.250, -30.01), (0.275, -27.48),
    (0.300, -25.16), (0.325, -23.01), (0.350, -21.01), (0.375, -19.13),
    (0.400, -17.36), (0.425, -15.67), (0.450, -14.07), (0.475, -12.53),
    (0.500, -11.06), (0.525, -9.64), (0.550, -8.26), (0.575, -6.93),
    (0.600, -5.63), (0.625, -4.37), (0.650, -3.14), (0.675, -1.93),
    (0.700, -0.75), (0.725, 0.40), (0.750, 1.54), (0.775, 2.66),
    (0.800, 3.76), (0.825, 4.84), (0.850, 5.90), (0.875, 6.95),
    (0.900, 7.99), (0.925, 9.01), (0.950, 10.02), (0.975, 11.02),
    (1.000, 12.00),
]


def normalized_for_db(db: float) -> float:
    """dB -> REAPER's normalized fader position, via the measured taper."""
    if db <= REAPER_FADER_LAW[0][1]:
        return REAPER_FADER_LAW[0][0]
    for (n0, d0), (n1, d1) in zip(REAPER_FADER_LAW, REAPER_FADER_LAW[1:]):
        if db <= d1:
            span = d1 - d0
            return n0 if span == 0 else n0 + (n1 - n0) * (db - d0) / span
    return REAPER_FADER_LAW[-1][0]


# "Track: Set mute for master track (MIDI CC/OSC only)" from REAPER's action list.
# The set variant, not the toggle (14), so console and REAPER cannot diverge.
MASTER_MUTE_ACTION = 18


class OscSurface(NamedTuple):
    """REAPER's OSC control-surface settings, read from its own config."""
    name: str
    send_to_port: int      # REAPER's listen port: where the bridge sends
    listen_on_port: int    # REAPER's device port: where the bridge receives
    device_ip: str


def config_path() -> Path:
    """Where REAPER keeps reaper.ini on this platform."""
    override = os.environ.get("REAPER_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".config" / "REAPER" / "reaper.ini"


def discover_osc_surface(path: Optional[Path] = None) -> Optional[OscSurface]:
    """Read REAPER's configured OSC surface so no ports need to be typed twice.

    The csurf line looks like:
        csurf_0=OSC "name" <mode> <local port> "<device ip>" <device port> ...
    where the local port is the one REAPER listens on and the device port is
    where REAPER sends its feedback -- so they are, respectively, where the
    bridge should send and where it should listen.
    """
    path = path or config_path()
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None

    count = 0
    surfaces = []
    for line in lines:
        if line.startswith("csurf_cnt="):
            try:
                count = int(line.split("=", 1)[1])
            except ValueError:
                count = 0
        elif line.startswith("csurf_"):
            surfaces.append(line.split("=", 1)[1] if "=" in line else "")
    if not count:
        return None  # configured but disabled, or none at all

    for entry in surfaces[:count]:
        try:
            fields = shlex.split(entry)
        except ValueError:
            continue
        if not fields or fields[0] != "OSC" or len(fields) < 6:
            continue
        try:
            return OscSurface(name=fields[1], send_to_port=int(fields[3]),
                              listen_on_port=int(fields[5]), device_ip=fields[4])
        except (ValueError, IndexError):
            continue
    return None


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
        self._send("/master/volume", normalized_for_db(e.db))

    def _on_master_mute(self, e: ev.MasterMuteChanged) -> None:
        # Default.ReaperOSC has no MASTER_MUTE pattern, so this goes through the
        # ACTION mechanism instead: action 18 is "Track: Set mute for master track
        # (MIDI CC/OSC only)", which sets rather than toggles, so it cannot drift
        # out of step with the console. Sent via the f/action/@/cc pattern.
        self._send(f"/action/{MASTER_MUTE_ACTION}/cc", 1.0 if e.muted else 0.0)

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
