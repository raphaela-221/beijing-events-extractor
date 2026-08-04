#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 2: open the editable event-list Excel for review.

The canonical event list is `01_event_list_output/Events List.xlsx`. Edit it
directly in Excel, save, and then run `extract` again to refresh the calendar
data.
"""
import argparse
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CANONICAL_EXCEL = ROOT.parent / "01_event_list_output" / "Events List.xlsx"


def parse_args():
    parser = argparse.ArgumentParser(description="Open the event-list Excel for review.")
    parser.add_argument(
        "--excel",
        default=str(CANONICAL_EXCEL),
        help="Path to the event-list Excel (default: ../01_event_list_output/Events List.xlsx).",
    )
    return parser.parse_args()


def open_file(path: Path):
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=True)
    elif system == "Windows":
        subprocess.run(["start", "", str(path)], check=True, shell=True)
    else:
        print(f"Please open this file manually: {path}", file=sys.stderr)


def main():
    args = parse_args()
    excel = Path(args.excel)
    if not excel.exists():
        print(f"ERROR: {excel} not found. Create it or run extract first.")
        return 1

    print(f"Opening {excel} for review...")
    print("  Edit the 'Events List' sheet directly, then save and re-run extract.")
    try:
        open_file(excel)
    except Exception as exc:
        print(f"Could not auto-open Excel: {exc}", file=sys.stderr)
        print(f"Please open manually: {excel}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
