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

from yamaha01v96i import events as ev  # noqa: E402
from yamaha01v96i import parser, protocol  # noqa: E402


def channel_label(index: Optional[int]) -> str:
    """Track index -> ch1-32 / ST1-4, matching the console's own naming."""
    if index is None:
        return ""
    if index < protocol.MONO_CHANNELS:
        return f"ch{index + 1}"
    return f"ST{index - protocol.MONO_CHANNELS + 1}"


def describe(event: ev.MixerEvent) -> Tuple[str, Optional[int], str]:
    """Return (label, channel index, human-readable value) for one event."""
    raw = list(event.raw)
    name = parser.identify(raw) or "?"

    if isinstance(event, ev.Keepalive):
        return "keepalive", None, ""
    if isinstance(event, ev.Ignored):
        return name, None, f"(ignored: {event.reason})"
    if isinstance(event, ev.ConsoleStatus):
        return event.kind, None, f"param {event.param} = {event.value}"
    if isinstance(event, ev.FaderMoved):
        return name, event.channel, f"raw={protocol.decode_value(raw):5d}  ({event.db:+.1f} dB)"
    if isinstance(event, ev.MasterFaderMoved):
        return name, None, f"raw={protocol.decode_value(raw):5d}  ({event.db:+.1f} dB)"
    if isinstance(event, ev.AuxSendMoved):
        return name, event.channel, f"aux {event.aux}  ({event.db:+.1f} dB)"
    if isinstance(event, ev.AuxMasterMoved):
        return name, None, f"aux {event.aux} master  ({event.db:+.1f} dB)"
    if isinstance(event, ev.BusFaderMoved):
        return name, None, f"bus {event.bus}  ({event.db:+.1f} dB)"
    if isinstance(event, ev.MuteChanged):
        return name, event.channel, "MUTED" if event.muted else "ON (unmuted)"
    if isinstance(event, ev.MasterMuteChanged):
        return name, None, "MUTED" if event.muted else "ON (unmuted)"
    if isinstance(event, ev.BusOnChanged):
        return name, None, f"bus {event.bus}: {'ON' if event.on else 'OFF'}"
    if isinstance(event, ev.AuxOnChanged):
        return name, None, f"aux {event.aux}: {'ON' if event.on else 'OFF'}"
    if isinstance(event, ev.PanMoved):
        return name, event.channel, f"{protocol.decode_value(raw):+4d} / 63  ({event.value:+.3f})"
    if isinstance(event, ev.SurroundMoved):
        return name, event.channel, f"{event.axis.upper()} {protocol.decode_value(raw):+4d} / 63"
    if isinstance(event, ev.SoloChanged):
        return name, event.channel, "SOLO" if event.soloed else "solo off"
    if isinstance(event, ev.EqChanged):
        who = {"master": "master",
               "aux": f"aux{(event.channel or 0) + 1}"}.get(
            event.selector, channel_label(event.channel))
        if event.gain_db is not None:
            return name, event.channel, f"{who} b{event.band} gain: {event.gain_db:+.1f} dB"
        if event.freq_hz is not None:
            return name, event.channel, f"{who} b{event.band} freq: {event.freq_hz:.0f} Hz"
        if event.q is not None:
            return name, event.channel, f"{who} b{event.band} Q: {event.q:.2f}"
        if event.filter_type is not None:
            return name, event.channel, f"{who} b{event.band} type: {event.filter_type}"
        return name, event.channel, f"{who} b{event.band} filter: {'ON' if event.enabled else 'OFF'}"
    return name, None, ""


def decode(data: List[int]) -> Tuple[str, Optional[int], str]:
    """Describe a raw payload, flagging anything the parser does not recognise."""
    event = parser.parse(data)
    if event is None:
        if len(data) >= 12:
            return "UNKNOWN", None, (f"sel={data[5]:#04x} param={data[6]} "
                                     f"ch={data[7]} value={protocol.decode_value(data)}")
        return "UNKNOWN", None, " ".join(f"{b:02X}" for b in data)
    return describe(event)


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

        if label == "eq":
            event = parser.parse(data)
            if isinstance(event, ev.EqChanged):
                who = "master" if event.selector == "master" else channel_label(event.channel)
                control = next(
                    (k for k, v in (("gain", event.gain_db), ("freq", event.freq_hz),
                                    ("Q", event.q), ("type", event.filter_type),
                                    ("filter", event.enabled)) if v is not None), "?")
                self.eq[f"{who} b{event.band} {control}"] = value
        elif label.startswith("master"):
            self.master[label] = value
        elif channel is not None:
            self.channels.setdefault(channel, {})[label] = value
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
        chan = f"{channel_label(row['channel']):<5}"
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
            put(stdscr, y, split, f"  {channel_label(chan):<6}{summary}")
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
