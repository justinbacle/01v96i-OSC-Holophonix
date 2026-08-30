"""Tests for the REAPER backend: config discovery, taper, and event mapping."""
from __future__ import annotations

import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backends.reaper import (  # noqa: E402
    MASTER_MUTE_ACTION, ReaperBackend, discover_osc_surface, normalized_for_db)
from yamaha01v96i import encoder, parse  # noqa: E402


class RecordingSender:
    def __init__(self):
        self.calls = []

    def send(self, address, *args):
        self.calls.append((address, args[0] if args else None))


def write_ini(directory: Path, body: str) -> Path:
    path = directory / "reaper.ini"
    path.write_text(textwrap.dedent(body).lstrip())
    return path


class DiscoverSurfaceTest(unittest.TestCase):
    def test_reads_ports_from_the_csurf_line(self):
        with TemporaryDirectory() as tmp:
            path = write_ini(Path(tmp), '''
                [reaper]
                csurf_0=OSC "01V96i" 5 8000 "127.0.0.1" 9000 1024 10 ""
                csurf_cnt=1
            ''')
            surface = discover_osc_surface(path)
        self.assertIsNotNone(surface)
        self.assertEqual(surface.name, "01V96i")
        self.assertEqual(surface.send_to_port, 8000)
        self.assertEqual(surface.listen_on_port, 9000)
        self.assertEqual(surface.device_ip, "127.0.0.1")

    def test_device_ip_port_mode_has_no_local_port(self):
        # Mode 7: REAPER receives on an ephemeral port, so field 3 is 0.
        with TemporaryDirectory() as tmp:
            path = write_ini(Path(tmp), '''
                csurf_0=OSC "01V96i" 7 0 "127.0.0.1" 9000 1024 10 ""
                csurf_cnt=1
            ''')
            surface = discover_osc_surface(path)
        self.assertEqual(surface.send_to_port, 0)
        self.assertEqual(surface.listen_on_port, 9000)

    def test_disabled_surface_is_ignored(self):
        with TemporaryDirectory() as tmp:
            path = write_ini(Path(tmp), '''
                csurf_0=OSC "01V96i" 5 8000 "127.0.0.1" 9000 1024 10 ""
                csurf_cnt=0
            ''')
            self.assertIsNone(discover_osc_surface(path))

    def test_non_osc_surfaces_are_skipped(self):
        with TemporaryDirectory() as tmp:
            path = write_ini(Path(tmp), '''
                csurf_0=HUI 1 16 4 5
                csurf_cnt=1
            ''')
            self.assertIsNone(discover_osc_surface(path))

    def test_missing_file(self):
        self.assertIsNone(discover_osc_surface(Path("/nonexistent/reaper.ini")))


class FaderTaperTest(unittest.TestCase):
    def test_measured_points(self):
        # 0 dB is not at the middle of REAPER's fader, nor at the top.
        self.assertAlmostEqual(normalized_for_db(0.0), 0.716, places=2)
        self.assertAlmostEqual(normalized_for_db(12.0), 1.0, places=3)

    def test_monotonic_and_clamped(self):
        values = [normalized_for_db(db) for db in range(-150, 13)]
        self.assertEqual(values, sorted(values))
        self.assertEqual(normalized_for_db(-500.0), 0.0)
        self.assertEqual(normalized_for_db(500.0), 1.0)


class EventMappingTest(unittest.TestCase):
    def setUp(self):
        self.sender = RecordingSender()
        self.backend = ReaperBackend(self.sender)

    def feed(self, payload):
        self.backend.handle(parse(payload))
        return self.sender.calls

    def test_channel_fader_sends_real_db(self):
        calls = self.feed(encoder.channel_fader_db(0, -20.0))
        self.assertEqual(calls[0][0], "/track/1/volume/db")
        self.assertAlmostEqual(calls[0][1], -20.0, delta=0.2)

    def test_mute_and_solo_are_booleans(self):
        self.assertEqual(self.feed(encoder.channel_on(2, False))[-1], ("/track/3/mute", 1))
        self.assertEqual(self.feed(encoder.solo(4, True))[-1], ("/track/5/solo", 1))

    def test_pan_is_centred_on_a_half(self):
        self.assertAlmostEqual(self.feed(encoder.pan(0, 0.0))[-1][1], 0.5, places=3)
        self.assertAlmostEqual(self.feed(encoder.pan(0, -1.0))[-1][1], 0.0, places=3)
        self.assertAlmostEqual(self.feed(encoder.pan(0, 1.0))[-1][1], 1.0, places=3)

    def test_master_fader_uses_the_taper_not_the_position(self):
        calls = self.feed(encoder.master_fader_db(0.0))
        self.assertEqual(calls[-1][0], "/master/volume")
        self.assertAlmostEqual(calls[-1][1], 0.716, places=2)

    def test_master_mute_goes_through_an_action(self):
        self.assertEqual(self.feed(encoder.master_on(False))[-1],
                         (f"/action/{MASTER_MUTE_ACTION}/cc", 1.0))

    def test_st_in_channels_reach_their_tracks(self):
        calls = self.feed(encoder.channel_fader_db(32, 0.0))
        self.assertEqual(calls[-1][0], "/track/33/volume/db")

    def test_unmapped_events_send_nothing(self):
        for payload in (encoder.eq_gain(0, 1, 6.0), encoder.aux_send_db(1, 0, -10.0),
                        encoder.bus_fader_db(1, -10.0), encoder.attenuation(0, -6.0)):
            self.backend.handle(parse(payload))
        self.assertEqual(self.sender.calls, [])


if __name__ == "__main__":
    unittest.main()
