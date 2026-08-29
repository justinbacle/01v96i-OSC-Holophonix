"""Tests for tools/capture.py — pure logic, no MIDI hardware or backend needed.

Run from the repository root with the project environment active:

    source .venv/bin/activate
    python3 -m unittest discover -s tests -v

The test vectors double as regression data for the SysEx masks registered in
main.py (see docs/01v96i.md §3 for the byte-layout reference).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import mido  # noqa: E402

from tools.capture import annotate, format_hex, run_capture  # noqa: E402


class FakePort:
    """Minimal mido input stand-in: an iterable of messages with a name."""

    name = "fake-test-port"

    def __init__(self, messages):
        self._messages = list(messages)

    def __iter__(self):
        return iter(self._messages)


# (payload, expected annotation) — one vector per known mask, plus one unknown.
SYSEX_VECTORS = [
    ([67, 16, 62, 127, 1, 28, 0, 2, 0, 0, 5, 13], "channel_fader"),
    ([67, 16, 62, 127, 1, 79, 0, 0, 0, 0, 7, 127], "master_fader"),
    ([67, 16, 62, 127, 1, 26, 0, 4, 0, 0, 0, 0], "channel_mute_form_a"),
    ([67, 16, 62, 26, 4, 90, 0, 4, 0, 0, 0, 1], "channel_mute_form_b"),
    ([67, 16, 62, 127, 1, 77, 0, 0, 0, 0, 0, 0], "master_mute_form_a"),
    ([67, 16, 62, 26, 4, 94, 0, 0, 0, 0, 0, 0], "master_mute_form_b"),
    ([67, 16, 62, 127, 1, 27, 0, 4, 0, 0, 0, 63], "pan"),
    ([67, 16, 62, 127, 1, 37, 5, 4, 0, 0, 0, 63], "surround_x"),
    ([67, 16, 62, 127, 1, 37, 6, 4, 127, 0, 0, 127], "surround_y"),
    ([67, 16, 62, 127, 1, 32, 3, 2, 0, 0, 1, 51], "eq"),
    ([67, 16, 62, 127, 1, 82, 3, 0, 0, 0, 1, 51], "eq"),
    ([67, 16, 62, 26, 127], "keepalive"),
    ([67, 16, 62, 127, 9, 1, 0, 0, 0, 0, 0, 0], None),  # unknown message
]


class AnnotateTest(unittest.TestCase):
    def test_known_and_unknown(self):
        for payload, expected in SYSEX_VECTORS:
            with self.subTest(payload=payload):
                self.assertEqual(annotate(list(payload)), expected)

    def test_format_hex(self):
        self.assertEqual(format_hex([67, 16, 62, 26, 127]), "F0 43 10 3E 1A 7F F7")


class RunCaptureTest(unittest.TestCase):
    def _messages(self):
        msgs = [mido.Message("sysex", data=payload) for payload, _ in SYSEX_VECTORS]
        msgs.append(mido.Message("control_change", control=7, value=64))
        return msgs

    def test_jsonl_log_and_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "cap.jsonl"
            counts = run_capture(FakePort(self._messages()), out, log_all=True)
            lines = [json.loads(line) for line in out.read_text().splitlines()]

        self.assertEqual(len(lines), len(SYSEX_VECTORS) + 1)
        for entry, (payload, expected) in zip(lines[:-1], SYSEX_VECTORS):
            self.assertEqual(entry["type"], "sysex")
            self.assertEqual(entry["dec"], payload)
            self.assertEqual(entry["known"], expected)
        self.assertEqual(lines[-1]["type"], "control_change")

        self.assertEqual(counts["channel_fader"], 1)
        self.assertEqual(counts["eq"], 2)
        self.assertEqual(counts["keepalive"], 1)
        self.assertEqual(counts["UNKNOWN"], 1)
        self.assertEqual(counts["other:control_change"], 1)

    def test_non_sysex_skipped_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "cap.jsonl"
            counts = run_capture(FakePort(self._messages()), out)
            lines = [json.loads(line) for line in out.read_text().splitlines()]

        self.assertEqual(len(lines), len(SYSEX_VECTORS))
        self.assertNotIn("other:control_change", counts)

    def test_unknown_only_still_logs_everything(self):
        # --unknown-only filters the console only; the JSONL stays complete.
        with tempfile.TemporaryDirectory() as tmp:
            out_a = Path(tmp) / "a.jsonl"
            out_b = Path(tmp) / "b.jsonl"
            run_capture(FakePort(self._messages()), out_a)
            run_capture(FakePort(self._messages()), out_b, unknown_only=True)

            decs_a = [json.loads(line)["dec"] for line in out_a.read_text().splitlines()]
            decs_b = [json.loads(line)["dec"] for line in out_b.read_text().splitlines()]
        self.assertEqual(decs_a, decs_b)


if __name__ == "__main__":
    unittest.main()