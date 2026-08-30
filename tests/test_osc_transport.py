"""Tests for the OSC transport: retargeting, source learning, malformed packets."""
from __future__ import annotations

import socket
import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from osc.osc_receiver import OSCReceiver  # noqa: E402
from osc.osc_sender import OSCSender  # noqa: E402


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TransportTest(unittest.TestCase):
    def setUp(self):
        self.received = []
        self.sources = []
        self.port = free_port()
        self.receiver = OSCReceiver("127.0.0.1", self.port,
                                    lambda a, args: self.received.append((a, args)),
                                    lambda ip, p: self.sources.append((ip, p)))
        self.receiver.start()
        self.addCleanup(self.receiver.stop)

    def test_round_trip(self):
        OSCSender("127.0.0.1", self.port).send("/track/1/mute", 1)
        self.assertTrue(wait_for(lambda: self.received))
        self.assertEqual(self.received[0][0], "/track/1/mute")

    def test_source_address_is_reported(self):
        OSCSender("127.0.0.1", self.port).send("/probe", 1)
        self.assertTrue(wait_for(lambda: self.sources))
        self.assertEqual(self.sources[0][0], "127.0.0.1")

    def test_sender_without_a_destination_is_silent(self):
        # Port 0 means "REAPER's address is not known yet"; sending must not raise.
        sender = OSCSender("127.0.0.1", 0)
        sender.send("/track/1/mute", 1)
        self.assertFalse(wait_for(lambda: self.received, timeout=0.3))

    def test_retarget_changes_destination(self):
        sender = OSCSender("127.0.0.1", 0)
        sender.retarget("127.0.0.1", self.port)
        sender.send("/track/1/mute", 1)
        self.assertTrue(wait_for(lambda: self.received))

    def test_malformed_packet_does_not_stop_the_server(self):
        # REAPER emits packets pythonosc rejects; one must not kill the receiver.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(b"\x00\x00\x00\x00", ("127.0.0.1", self.port))
        time.sleep(0.2)
        OSCSender("127.0.0.1", self.port).send("/track/1/mute", 1)
        self.assertTrue(wait_for(lambda: self.received))


if __name__ == "__main__":
    unittest.main()
