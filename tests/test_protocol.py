"""Unit tests for the wire-level conversions in yamaha01v96i.protocol."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from yamaha01v96i import protocol as p  # noqa: E402


class ValueFieldTest(unittest.TestCase):
    def test_round_trip(self):
        for value in (-8388608, -180, -63, -1, 0, 1, 63, 823, 1023, 180, 8388607):
            self.assertEqual(p.decode_value([0] * 8 + p.encode_value(value)), value)

    def test_negatives_are_twos_complement(self):
        # Full-left pan as captured from the console.
        self.assertEqual(p.decode_value([0, 0, 0, 0, 0, 0, 0, 0, 127, 127, 127, 65]), -63)

    def test_encode_produces_seven_bit_bytes(self):
        for value in (-1, -180, 1023):
            self.assertTrue(all(0 <= b <= 127 for b in p.encode_value(value)))


class ChannelNumberingTest(unittest.TestCase):
    def test_mono_channels_map_directly(self):
        self.assertEqual(p.channel_index(0), 0)
        self.assertEqual(p.channel_index(31), 31)

    def test_st_in_left_slots_follow_the_mono_channels(self):
        for i in range(p.ST_IN_COUNT):
            self.assertEqual(p.channel_index(p.ST_IN_FIRST + 2 * i),
                             p.MONO_CHANNELS + i)

    def test_st_in_right_slots_are_dropped(self):
        for i in range(p.ST_IN_COUNT):
            self.assertIsNone(p.channel_index(p.ST_IN_FIRST + 2 * i + 1))

    def test_out_of_range_is_rejected(self):
        self.assertFalse(p.is_channel_byte(p.ST_IN_FIRST + 2 * p.ST_IN_COUNT))
        self.assertIsNone(p.channel_index(127))


class FaderLawTest(unittest.TestCase):
    def test_measured_anchors(self):
        self.assertAlmostEqual(p.fader_db(823), 0.0, places=2)
        self.assertAlmostEqual(p.fader_db(1023), 10.0, places=2)
        self.assertAlmostEqual(p.fader_db(1023, unity_top=True), 0.0, places=2)

    def test_monotonic(self):
        values = [p.fader_db(raw) for raw in range(0, 1024, 8)]
        self.assertEqual(values, sorted(values))

    def test_round_trip_within_one_step(self):
        for raw in (0, 100, 331, 552, 823, 1000, 1023):
            self.assertAlmostEqual(p.fader_raw(p.fader_db(raw)), raw, delta=1)

    def test_clamped_outside_the_range(self):
        self.assertEqual(p.fader_db(-50), p.fader_db(0))
        self.assertEqual(p.fader_db(99999), p.fader_db(p.FADER_MAX_RAW))


class EqConversionTest(unittest.TestCase):
    def test_frequency_endpoints(self):
        self.assertAlmostEqual(p.eq_freq_hz(p.EQ_FREQ_RAW_MIN), p.EQ_FREQ_HZ_MIN, places=1)
        self.assertAlmostEqual(p.eq_freq_hz(p.EQ_FREQ_RAW_MAX), p.EQ_FREQ_HZ_MAX, places=0)

    def test_frequency_round_trip(self):
        for hz in (21.2, 100.0, 1000.0, 10000.0, 20000.0):
            self.assertAlmostEqual(p.eq_freq_hz(p.eq_freq_raw(hz)) / hz, 1.0, delta=0.05)

    def test_q_endpoints(self):
        self.assertAlmostEqual(p.eq_q(0), 10.0, places=2)
        self.assertAlmostEqual(p.eq_q(40), 0.1, places=2)

    def test_gain_is_tenths_of_a_db(self):
        self.assertEqual(p.eq_gain_raw(18.0), 180)
        self.assertEqual(p.eq_gain_raw(-18.0), -180)


if __name__ == "__main__":
    unittest.main()
