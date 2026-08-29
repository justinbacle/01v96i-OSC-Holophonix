"""Golden test: every captured message must produce the same OSC calls as today.

The fixtures are real console captures, so this pins the whole decode pipeline --
masks, dispatch order and value conversion -- against refactoring. Regenerate the
snapshot deliberately with `python3 tests/test_golden_dispatch.py --update` when a
behaviour change is intended, and review the diff.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from main import OSC_Handler, SysexDispatcher, SysexHandler  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "captured_messages.json"
SNAPSHOT = REPO_ROOT / "tests" / "fixtures" / "golden_osc.json"


class RecordingSender:
    """Stands in for OSCSender, capturing what would have gone over the wire."""

    def __init__(self) -> None:
        self.calls: List[Any] = []

    def send(self, address: str, *args) -> None:
        rounded = [round(a, 6) if isinstance(a, float) else a for a in args]
        self.calls.append([address, *rounded])


def build_dispatcher(sender: RecordingSender) -> SysexDispatcher:
    """Mirror main.main()'s handler registration order."""
    dispatcher = SysexDispatcher(OSC_Handler(sender))
    for _name, mask, handler in SysexHandler.REGISTRY:
        dispatcher.add_handler(mask, handler)
    return dispatcher


def run_all(messages: List[List[int]]) -> List[Any]:
    sender = RecordingSender()
    dispatcher = build_dispatcher(sender)
    for data in messages:
        dispatcher.dispatch(data)
    return sender.calls


class GoldenDispatchTest(unittest.TestCase):
    def test_osc_output_unchanged(self):
        messages = json.loads(FIXTURES.read_text())
        expected = json.loads(SNAPSHOT.read_text())
        self.assertEqual(run_all(messages), expected)


if __name__ == "__main__":
    if "--update" in sys.argv:
        msgs = json.loads(FIXTURES.read_text())
        SNAPSHOT.write_text(json.dumps(run_all(msgs), indent=1) + "\n")
        print(f"snapshot written: {SNAPSHOT} ({len(json.loads(SNAPSHOT.read_text()))} calls)")
    else:
        unittest.main()
