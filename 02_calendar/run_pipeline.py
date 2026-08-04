#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""北京大事件 · 整合总览 pipeline 入口

把整个流程串成一条线：
    canonical Events List.xlsx → events_data → calendar 页面 → Ark 主题润色 → 分享包

Usage:
    python3 run_pipeline.py extract            # 从默认 canonical Excel 抽出 High 事件
    python3 run_pipeline.py eventlist          # 打开 canonical Excel 人工核对
    python3 run_pipeline.py calendar           # 确认 calendar 页面可用
    python3 run_pipeline.py themes --year 2026 # 增量生成本月观察
    python3 run_pipeline.py all --year 2026    # 一次性跑 extract + themes + package
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def run(cmd, **kwargs):
    print(f"\n▶ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def cmd_extract(args):
    cmd = [sys.executable, str(ROOT / "extract_demo_data.py")]
    if args.source:
        cmd += ["--source", args.source]
    if args.output_dir:
        cmd += ["--output-dir", args.output_dir]
    run(cmd)
    print("\n✓ Step 1 done: canonical Excel → events_data.json / events_data.js / state/last_run.json")


def cmd_dedup(args):
    cmd = [sys.executable, str(ROOT / "dedup_canonical_excel.py")]
    if args.dry_run:
        cmd += ["--dry-run"]
    if args.source:
        cmd += ["--source", args.source]
    run(cmd)
    print("\n✓ Dedup done: canonical Excel cleaned in place (.bak backup created).")
    print("  Re-run `python3 run_pipeline.py extract` to refresh events_data.")


def cmd_eventlist(args):
    cmd = [sys.executable, str(ROOT / "build_event_list.py")]
    if args.excel:
        cmd += ["--excel", args.excel]
    run(cmd)
    print("\n✓ Step 2 done: canonical Events List.xlsx is open for review.")
    print("  Edit the 'Events List' sheet directly, save, then run:")
    print("    python3 run_pipeline.py extract")


def cmd_calendar(args):
    root = Path(args.output_dir) if args.output_dir else ROOT
    required = ["index.html", "month.html", "timeline.html", "events_data.js", "common.js", "calendar.css"]
    missing = [f for f in required if not (root / f).exists()]
    if missing:
        print(f"ERROR: missing calendar files: {', '.join(missing)}")
        print("  Run `python3 run_pipeline.py extract` first.")
        return 1

    canonical_excel = Path(__file__).parent.parent / "01_event_list_output" / "Events List.xlsx"
    js = root / "events_data.js"
    if canonical_excel.exists() and js.exists() and canonical_excel.stat().st_mtime > js.stat().st_mtime:
        print("\n⚠️  Events List.xlsx is newer than events_data.js.")
        print("  If you edited the Excel, re-run `python3 run_pipeline.py extract` before opening the calendar.")
    else:
        print("\n✓ Step 3 ready: calendar pages are built on top of the reviewed data.")
    print(f"  Open {root / 'index.html'} to view the overview.")
    return 0


def cmd_themes(args):
    cmd = [sys.executable, str(ROOT / "generate_monthly_themes.py")]
    if args.year:
        cmd += ["--year", str(args.year)]
    if args.month:
        cmd += ["--month", args.month]
    if args.min_events:
        cmd += ["--min-events", str(args.min_events)]
    run(cmd)
    print("\n✓ Step 4 done: monthly themes enriched by Ark.")


def cmd_package(args):
    cmd = [sys.executable, str(ROOT / "package_output.py")]
    if args.output_dir:
        cmd += ["--output-dir", args.output_dir]
    if args.source_dir:
        cmd += ["--source-dir", args.source_dir]
    run(cmd)
    print("\n✓ Step 5 done: packaged viewer-facing files for sharing.")


def cmd_all(args):
    cmd_extract(args)
    if args.themes:
        cmd_themes(args)
    cmd_calendar(args)
    if args.package:
        cmd_package(args)
    print("\n✓ All requested steps finished.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Beijing major events calendar pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Typical workflow:
  1. Maintain ../01_event_list_output/Events List.xlsx (the canonical event list).
  2. python3 run_pipeline.py extract
  3. python3 run_pipeline.py themes --year 2026   (incremental: only changed months call Ark)
  4. python3 run_pipeline.py calendar
  5. python3 run_pipeline.py package
  6. Upload the 02_web_output/ folder to OneDrive and share the folder link.

To force re-generate a single month: python3 run_pipeline.py themes --month 2026-06
To keep a manual HTML tweak across packages, put the modified file in 02_calendar/overrides/
""",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # extract
    p_extract = sub.add_parser("extract", help="Extract High events from raw Excel")
    p_extract.add_argument("--source", default=None, help="Path to source Excel")
    p_extract.add_argument("--output-dir", default=None, help="Output directory")
    p_extract.set_defaults(func=cmd_extract)

    # dedup
    p_dedup = sub.add_parser("dedup", help="Deduplicate the canonical Events List.xlsx in place")
    p_dedup.add_argument("--source", default=None, help="Path to Excel (default: canonical)")
    p_dedup.add_argument("--dry-run", action="store_true", help="Report only, no write")
    p_dedup.set_defaults(func=cmd_dedup)

    # eventlist
    p_eventlist = sub.add_parser("eventlist", help="Open event-list Excel for review")
    p_eventlist.add_argument("--excel", default=None, help="Path to event-list Excel")
    p_eventlist.set_defaults(func=cmd_eventlist)

    # calendar
    p_calendar = sub.add_parser("calendar", help="Verify calendar pages are ready")
    p_calendar.add_argument("--output-dir", default=None, help="Demo directory")
    p_calendar.set_defaults(func=cmd_calendar)

    # themes
    p_themes = sub.add_parser("themes", help="Generate monthly themes via Ark")
    p_themes.add_argument("--year", type=int, default=None, help="Year to generate")
    p_themes.add_argument("--month", default=None, help="Single month YYYY-MM")
    p_themes.add_argument("--min-events", type=int, default=5, help="Skip months with fewer events")
    p_themes.set_defaults(func=cmd_themes)

    # package
    p_package = sub.add_parser("package", help="Package viewer-facing files into output/ folder")
    p_package.add_argument("--source-dir", default=None, help="Directory containing calendar files")
    p_package.add_argument("--output-dir", default=None, help="Directory to write packaged files")
    p_package.set_defaults(func=cmd_package)

    # all
    p_all = sub.add_parser("all", help="Run extract + eventlist + optional themes + calendar + optional package")
    p_all.add_argument("--source", default=None, help="Path to source Excel")
    p_all.add_argument("--output-dir", default=None, help="Output directory")
    p_all.add_argument("--year", type=int, default=None, help="Year for themes")
    p_all.add_argument("--themes", action="store_true", help="Also run Ark theme enrichment")
    p_all.add_argument("--package", action="store_true", help="Also package output folder for sharing")
    p_all.add_argument("--min-events", type=int, default=5, help="Skip months with fewer events")
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
