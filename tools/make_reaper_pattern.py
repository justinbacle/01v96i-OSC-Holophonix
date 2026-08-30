#!/usr/bin/env python3
"""Create a REAPER OSC pattern file sized for the console.

REAPER's Default.ReaperOSC exposes only 8 tracks (DEVICE_TRACK_COUNT), so tracks
beyond that are unreachable in both directions. This writes a copy with a larger
count into REAPER's user OSC directory; select it as the surface's "Pattern
config" in Preferences -> Control/OSC/web.

Usage:
    python3 tools/make_reaper_pattern.py            # 32 tracks, named 01V96i
    python3 tools/make_reaper_pattern.py --tracks 16
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backends.reaper import config_path  # noqa: E402


def default_pattern_candidates() -> List[Path]:
    """Where REAPER's stock Default.ReaperOSC lives, per platform."""
    candidates: List[Path] = []
    config = config_path()
    if config is not None:                       # user copy, written by REAPER
        candidates.append(config.parent / "OSC" / "Default.ReaperOSC")
    if sys.platform == "darwin":
        candidates.append(Path("/Applications/REAPER.app/Contents/Plugins/Default.ReaperOSC"))
    elif sys.platform.startswith("win"):
        for root in (r"C:\Program Files\REAPER (x64)", r"C:\Program Files\REAPER"):
            candidates.append(Path(root) / "Plugins" / "Default.ReaperOSC")
    else:
        candidates.append(Path("/opt/REAPER/Plugins/Default.ReaperOSC"))
        candidates.append(Path("/usr/share/reaper/Plugins/Default.ReaperOSC"))
    return candidates


def find_default_pattern() -> Optional[Path]:
    for candidate in default_pattern_candidates():
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tracks", type=int, default=32, help="DEVICE_TRACK_COUNT to set")
    ap.add_argument("--name", default="01V96i", help="pattern file name, without extension")
    ap.add_argument("--source", type=Path, help="path to Default.ReaperOSC")
    args = ap.parse_args()

    source = args.source or find_default_pattern()
    if source is None or not source.is_file():
        print("Could not find Default.ReaperOSC. Looked in:", file=sys.stderr)
        for candidate in default_pattern_candidates():
            print(f"  {candidate}", file=sys.stderr)
        print("Pass --source with its path.", file=sys.stderr)
        return 1

    config = config_path()
    if config is None:
        print("Could not find reaper.ini, so cannot place the pattern file.",
              file=sys.stderr)
        return 1
    target_dir = config.parent / "OSC"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{args.name}.ReaperOSC"

    # newline="" keeps REAPER's CRLF endings byte-for-byte.
    text = source.read_text(encoding="utf-8", errors="replace", newline="")
    patched, count = re.subn(r"(?m)^DEVICE_TRACK_COUNT[ \t]+\d+",
                             f"DEVICE_TRACK_COUNT {args.tracks}", text, count=1)
    if not count:
        print(f"No DEVICE_TRACK_COUNT line in {source}", file=sys.stderr)
        return 1
    target.write_text(patched, encoding="utf-8", newline="")

    print(f"wrote {target}\n  from {source}\n  DEVICE_TRACK_COUNT = {args.tracks}")
    print(f"\nIn REAPER: Preferences > Control/OSC/web > your OSC device >\n"
          f"  Pattern config = {args.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
