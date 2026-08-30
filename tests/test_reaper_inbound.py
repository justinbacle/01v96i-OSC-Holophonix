"""Tests for REAPER's OSC feedback being applied to the console."""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backends.reaper_inbound import ECHO_WINDOW_S, ReaperInbound  # noqa: E402
from yamaha01v96i import parse  # noqa: E402
from yamaha01v96i import events as ev  # noqa: E402


class RecordingPort:
    """Stands in for a mido output port."""

    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(list(message.bytes())[1:-1])

    def events(self):
        return [parse(payload) for payload in self.sent]


class InboundTest(unittest.TestCase):
    def setUp(self):
        self.port = RecordingPort()
        self.inbound = ReaperInbound(self.port)

    def test_volume_becomes_a_fader_move(self):
        self.inbound.handle("/track/1/volume/db", (-20.0,))
        event = self.port.events()[0]
        self.assertIsInstance(event, ev.FaderMoved)
        self.assertEqual(event.channel, 0)
        self.assertAlmostEqual(event.db, -20.0, delta=0.2)

    def test_mute_polarity_is_inverted(self):
        # REAPER: 1 = muted. Console ON: 1 = unmuted.
        self.inbound.handle("/track/3/mute", (1.0,))
        event = self.port.events()[0]
        self.assertIsInstance(event, ev.MuteChanged)
        self.assertEqual(event.channel, 2)
        self.assertTrue(event.muted)

    def test_pan_is_recentred(self):
        self.inbound.handle("/track/1/pan", (0.5,))
        self.assertAlmostEqual(self.port.events()[0].value, 0.0, places=2)
        self.inbound.handle("/track/1/pan", (0.0,))
        self.assertAlmostEqual(self.port.events()[1].value, -1.0, places=2)

    def test_solo(self):
        self.inbound.handle("/track/5/solo", (1.0,))
        event = self.port.events()[0]
        self.assertIsInstance(event, ev.SoloChanged)
        self.assertEqual(event.channel, 4)
        self.assertTrue(event.soloed)

    def test_master_volume(self):
        self.inbound.handle("/master/volume", (1.0,))
        self.assertIsInstance(self.port.events()[0], ev.MasterFaderMoved)

    def test_unknown_addresses_are_ignored(self):
        for address in ("/track/1/volume/str", "/click", "/track/name", "/nonsense"):
            self.inbound.handle(address, (1.0,))
        self.assertEqual(self.port.sent, [])

    def test_empty_arguments_are_ignored(self):
        self.inbound.handle("/track/1/volume/db", ())
        self.assertEqual(self.port.sent, [])

    def test_our_own_echo_is_suppressed(self):
        # What the bridge just sent must not be applied when REAPER echoes it,
        # or the console fights the operator's hand.
        self.inbound.note_sent("/track/1/volume/db", -20.0)
        self.inbound.handle("/track/1/volume/db", (-20.0,))
        self.assertEqual(self.port.sent, [])

    def test_a_genuine_change_is_not_suppressed(self):
        self.inbound.note_sent("/track/1/volume/db", -20.0)
        self.inbound.handle("/track/1/volume/db", (-5.0,))
        self.assertEqual(len(self.port.sent), 1)

    def test_echo_suppression_expires(self):
        self.inbound.note_sent("/track/1/volume/db", -20.0)
        self.inbound._sent["/track/1/volume/db"] = (-20.0, time.time() - ECHO_WINDOW_S - 1)
        self.inbound.handle("/track/1/volume/db", (-20.0,))
        self.assertEqual(len(self.port.sent), 1)


if __name__ == "__main__":
    unittest.main()
