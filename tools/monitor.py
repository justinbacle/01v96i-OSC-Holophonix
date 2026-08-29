#!/usr/bin/env python3
"""Live TUI monitor for 01V96i MIDI SysEx traffic.

A curses front-end to the same masks the bridge uses. Shows every incoming
message decoded in real time, keeps a running state table per channel, and
highlights anything the bridge does not recognise — those are the messages
worth discovering (EQ bands 2-4, buses, other console modes).

Everything is also appended to a JSONL log, so a session can be analysed
afterwards exactly like a ``tools/capture.py`` run.

Usage:
    python3 tools/monitor.py                 # auto-detect the console port
    python3 tools/monitor.py --port "..."    # explicit port name
    python3 tools/monitor.py --out log.jsonl # explicit log file

Keys:
    q  quit          space  pause/resume      c  clear stream
    k  show/hide keepalive                    u  unknown messages only
"""
from __future__ import annotations

import argparse
import curses
import json
import sys
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import mido
except ImportError:  # pragma: no cover
    print("mido is required: see README § Setup (venv + requirements.txt)", file=sys.stderr)
    sys.exit(1)

from main import SysexHandler  # noqa: E402

KNOWN_MESSAGES = [
    ("keepalive", SysexHandler.ignore_specific_message_mask),
    ("master_fader", SysexHandler.master_fader_mask),
    ("master_mute_a", SysexHandler.master_mute_mask_1),
    ("master_mute_b", SysexHandler.master_mute_mask_2),
    ("channel_fader", SysexHandler.channel_fader_mask),
    ("channel_mute_a", SysexHandler.mute_mask_1),
    ("channel_mute_b", SysexHandler.mute_mask_2),
    ("pan", SysexHandler.pan_mask),
    ("surround_y", SysexHandler.y_mask),
    ("surround_x", SysexHandler.x_mask),
    ("eq", SysexHandler.eq_mask),
]




def decode(data: List[int]) -> Tuple[str, Optional[int], str]:
    """Return (label, channel, human-readable value) for one SysEx payload."""
    label = "UNKNOWN"
    for name, mask_fn in KNOWN_MESSAGES:
        if mask_fn(data):
            label = name
            break

    if label == "keepalive":
        return label, None, ""
    if label == "UNKNOWN":
        if len(data) >= 12:
            return label, data[7], f"sel={data[5]:#04x} param={data[6]} u={data[10]} v={data[11]}"
        return label, None, ""

    channel = data[7]
    if label in ("channel_fader", "master_fader"):
        raw = SysexHandler.decode_value(data)
        db = SysexHandler.fader_db(raw, master=(label == "master_fader"))
        shown = "-inf" if raw <= 0 else f"{db:+.1f} dB"
        return label, channel, f"raw={raw:5d}  ({shown})"
    if label.startswith(("channel_mute", "master_mute")):
        return label, channel, "ON (unmuted)" if data[11] == 1 else "MUTED"
    if label in ("pan", "surround_x", "surround_y"):
        value = SysexHandler.decode_value(data)
        return label, channel, f"{value:+4d} / 63  ({value / 63:+.3f})"
    if label == "eq":
        who = "master" if data[5] == 82 else f"ch{channel + 1}"
        band, control = SysexHandler.EQ_PARAMS[data[6]]
        param = f"b{band} {control}"
        if control == "gain":
            raw = SysexHandler.decode_value(data)
            return label, channel, f"{who} {param}: raw={raw:+5d} ({raw / 10:+.1f} dB)"
        if control == "freq":
            v = data[11]
            freq = 21.2 * ((20000 / 21.2) ** ((v - 5) / (124 - 5)))
            return label, channel, f"{who} {param}: v={v:3d} ({freq:.0f} Hz)"
        raw = SysexHandler.decode_value(data)
        if control == "enable":
            return label, channel, f"{who} {param}: {'ON' if raw else 'OFF'}"
        kind = SysexHandler.EQ_TYPE_CODES.get(raw, "Bell")
        if kind == "Bell":
            q = 10 * (0.1 / 10) ** (raw / 40)
            return label, channel, f"{who} {param}: raw={raw:3d} (Bell  Q={q:.2f})"
        return label, channel, f"{who} {param}: raw={raw:3d} ({kind})"
    return label, channel, ""


class MonitorState:
    """Rolling stream plus latest-value tables, rendered by the curses loop."""

    def __init__(self, maxlen: int = 500) -> None:
        self.stream: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self.counts: Counter = Counter()
        self.channels: Dict[int, Dict[str, str]] = {}
        self.master: Dict[str, str] = {}
        self.eq: Dict[str, str] = {}
        self.started = time.time()
        self.total = 0

    def add(self, data: List[int], hex_str: str) -> Dict[str, Any]:
        label, channel, value = decode(data)
        self.counts[label] += 1
        self.total += 1

        last = self.stream[-1] if self.stream else None
        if last and last["label"] == label and last["value"] == value and last["channel"] == channel:
            last["repeat"] += 1
            last["ts"] = time.time()
        else:
            self.stream.append(
                {
                    "ts": time.time(),
                    "label": label,
                    "channel": channel,
                    "value": value,
                    "hex": hex_str,
                    "repeat": 1,
                }
            )

        if label in ("channel_fader", "pan", "surround_x", "surround_y") or label.startswith("channel_mute"):
            if channel is not None:
                self.channels.setdefault(channel, {})[label] = value
        elif label.startswith("master"):
            self.master[label] = value
        elif label == "eq_band_1":
            who = "master" if data[5] == 82 else f"ch{data[7] + 1}"
            self.eq[f"{who} {EQ_PARAM_NAMES.get(data[6], data[6])}"] = value
        return {"label": label, "channel": channel, "value": value}


def pick_port(name: Optional[str]) -> str:
    """Return an input port name: the one given, or the first 01V96i port."""
    ports = mido.get_input_names()  # pyright: ignore[reportAttributeAccessIssue]
    if name:
        matches = [p for p in ports if name.lower() in p.lower()]
        if not matches:
            raise SystemExit(f"No MIDI input matching {name!r}.\nAvailable:\n  " + "\n  ".join(ports))
        return matches[0]
    console = [p for p in ports if "01V96i" in p]
    if not console:
        raise SystemExit("No 01V96i MIDI input found.\nAvailable:\n  " + "\n  ".join(ports))
    return console[0]


def put(win: "curses._CursesWindow", y: int, x: int, text: str, attr: int = 0) -> None:
    """Write clipped text, tolerating the bottom-right cell that makes curses raise."""
    height, width = win.getmaxyx()
    if not (0 <= y < height) or x >= width:
        return
    space = width - x
    clipped = text[:space]
    if y == height - 1 and len(clipped) == space:
        clipped = clipped[:-1]  # last cell of the last row advances the cursor off-screen
    if not clipped:
        return
    try:
        win.addnstr(y, x, clipped, len(clipped), attr)
    except curses.error:
        pass


def draw(stdscr: "curses._CursesWindow", state: MonitorState, port_name: str, flags: Dict[str, bool]) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    split = max(48, width - 44)

    elapsed = time.time() - state.started
    rate = state.total / elapsed if elapsed > 0 else 0.0
    header = f" {port_name}   {state.total} msgs   {rate:.1f}/s   {elapsed:.0f}s "
    if flags["paused"]:
        header += "  [PAUSED]"
    if flags["unknown_only"]:
        header += "  [UNKNOWN ONLY]"
    if not flags["show_keepalive"]:
        header += "  [keepalive hidden]"
    put(stdscr, 0, 0, header.ljust(width), curses.color_pair(1) | curses.A_BOLD)

    rows = [r for r in state.stream if flags["show_keepalive"] or r["label"] != "keepalive"]
    if flags["unknown_only"]:
        rows = [r for r in rows if r["label"] == "UNKNOWN"]
    for i, row in enumerate(rows[-(height - 3):]):
        y = 1 + i
        if y >= height - 1:
            break
        stamp = datetime.fromtimestamp(row["ts"]).strftime("%H:%M:%S")
        chan = f"ch{row['channel'] + 1:<2}" if row["channel"] is not None else "   "
        rep = f" x{row['repeat']}" if row["repeat"] > 1 else ""
        attr = curses.color_pair(3) | curses.A_BOLD if row["label"] == "UNKNOWN" else 0
        put(stdscr, y, 0, f"{stamp} {row['label']:<15} {chan} {row['value']}{rep}"[: split - 1], attr)

    y = 1
    put(stdscr, y, split, "COUNTS", curses.color_pair(2) | curses.A_BOLD)
    y += 1
    for label, n in state.counts.most_common(8):
        if y >= height - 1:
            break
        put(stdscr, y, split, f"  {label:<16}{n:>6}")
        y += 1

    for title, table in (("MASTER", state.master), ("EQ", state.eq)):
        if not table or y >= height - 2:
            continue
        y += 1
        put(stdscr, y, split, title, curses.color_pair(2) | curses.A_BOLD)
        y += 1
        for key, value in table.items():
            if y >= height - 1:
                break
            put(stdscr, y, split, f"  {key}: {value}")
            y += 1

    if state.channels and y < height - 2:
        y += 1
        put(stdscr, y, split, "CHANNELS", curses.color_pair(2) | curses.A_BOLD)
        y += 1
        for chan in sorted(state.channels):
            if y >= height - 1:
                break
            parts = state.channels[chan]
            summary = " ".join(f"{k.replace('channel_', '')}={v.split('(')[0].strip()}" for k, v in parts.items())
            put(stdscr, y, split, f"  ch{chan + 1:<3}{summary}")
            y += 1

    footer = " q quit   space pause   c clear   k keepalive   u unknown-only "
    put(stdscr, height - 1, 0, footer.ljust(width), curses.color_pair(1))
    stdscr.refresh()


def run(stdscr: "curses._CursesWindow", port_name: str, out_path: Path) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(2, curses.COLOR_CYAN, -1)
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_YELLOW)

    state = MonitorState()
    flags = {"paused": False, "show_keepalive": False, "unknown_only": False}
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with mido.open_input(port_name) as inport, out_path.open("a") as log:  # pyright: ignore
        last_draw = 0.0
        while True:
            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                return
            if key == ord(" "):
                flags["paused"] = not flags["paused"]
            elif key in (ord("c"), ord("C")):
                state.stream.clear()
            elif key in (ord("k"), ord("K")):
                flags["show_keepalive"] = not flags["show_keepalive"]
            elif key in (ord("u"), ord("U")):
                flags["unknown_only"] = not flags["unknown_only"]

            for msg in inport.iter_pending():
                if msg.type != "sysex" or flags["paused"]:
                    continue
                data = list(msg.bytes())[1:-1]
                hex_str = " ".join(f"{b:02X}" for b in msg.bytes())
                info = state.add(data, hex_str)
                log.write(
                    json.dumps(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "type": "sysex",
                            "hex": hex_str,
                            "dec": data,
                            "known": info["label"],
                            "value": info["value"],
                        }
                    )
                    + "\n"
                )
                log.flush()

            now = time.time()
            if now - last_draw > 0.05:
                draw(stdscr, state, port_name, flags)
                last_draw = now
            time.sleep(0.005)


def main() -> int:
    parser = argparse.ArgumentParser(description="Live TUI monitor for 01V96i SysEx traffic.")
    parser.add_argument("--port", help="MIDI input port name (substring match); default: first 01V96i port")
    parser.add_argument("--out", default=None, help="JSONL log file (default: captures/monitor_<timestamp>.jsonl)")
    args = parser.parse_args()

    port_name = pick_port(args.port)
    out_path = (
        Path(args.out)
        if args.out
        else REPO_ROOT / "captures" / f"monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    curses.wrapper(run, port_name, out_path)
    print(f"Log written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
