#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 5: package only the files needed for viewing/sharing into a clean output folder.

This produces a folder you can upload straight to OneDrive and share as a link.

Usage:
    python3 package_output.py
    python3 package_output.py --output-dir ./02_web_output
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PROJECT_ROOT = ROOT.parent
HERE = Path(__file__).resolve().parent

# The canonical, manually-edited event list lives in 01_event_list_output.
CANONICAL_EXCEL = PROJECT_ROOT / "01_event_list_output" / "Events List.xlsx"

# Files that the viewer actually needs. Everything else (scripts, source Excel,
# screenshots, design references) is left behind.
VIEWER_FILES = [
    "index.html",
    "month.html",
    "timeline.html",
    "common.js",
    "calendar.css",
    "events_data.js",
    "Events List.xlsx",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Package viewer-facing files into a clean output folder."
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "02_web_output"),
        help="Directory to write the packaged files.",
    )
    parser.add_argument(
        "--source-dir",
        default=str(ROOT),
        help="Directory containing the calendar files.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    source = Path(args.source_dir)
    out = Path(args.output_dir)

    # 打包前守卫：canonical 若被 openpyxl 往返损坏（sharedStrings/printerSettings
    # 被削、table 错位），中止打包，坏文件永远 ship 不出去。
    if CANONICAL_EXCEL.exists():
        rc = subprocess.run(
            [sys.executable, str(HERE / "verify_canonical.py"),
             "--excel", str(CANONICAL_EXCEL), "--quiet"],
            capture_output=True, text=True,
        )
        if rc.returncode != 0:
            print("ERROR: canonical 结构损坏，中止打包（防坏文件发布）：")
            print(rc.stdout)
            print("  修复：用 02_calendar 干净 base 重铺 canonical + 重跑 enrich（XML 写），勿发布坏文件。")
            return 1

    missing = [f for f in VIEWER_FILES if not (source / f).exists()]
    if missing:
        print(f"ERROR: missing required files: {', '.join(missing)}")
        print("  Run `python3 run_pipeline.py extract` first.")
        return 1

    # Preserve the output folder itself (so a OneDrive share link stays valid).
    # Copy/overwrite the current files. Files not in the whitelist (VIEWER_FILES
    # + README.txt + overrides) are removed to keep the share package clean;
    # place any extra assets in the overrides/ directory so they survive packaging.
    out.mkdir(parents=True, exist_ok=True)

    output_files = set(VIEWER_FILES + ["README.txt"])
    for name in VIEWER_FILES:
        if name == "Events List.xlsx" and CANONICAL_EXCEL.exists():
            shutil.copy2(CANONICAL_EXCEL, out / name)
        else:
            shutil.copy2(source / name, out / name)

    # Apply manual overrides last so they take precedence over generated files.
    overrides_dir = source / "overrides"
    if overrides_dir.exists():
        for override in overrides_dir.iterdir():
            if override.is_file():
                shutil.copy2(override, out / override.name)
                output_files.add(override.name)
                print(f"  applied override: {override.name}")

    # Reader-facing quick start (not for the operator).
    readme = out / "README.txt"
    readme.write_text(
        "北京大事件 · 整合总览\n"
        "=====================\n"
        "本文件夹是一个可离线浏览的静态页面。\n"
        "\n"
        "如何查看：\n"
        "  1. 把整个文件夹保存到本地（或保持 OneDrive 同步）。\n"
        "  2. 双击 index.html，用浏览器打开。\n"
        "  3. 页面内可切换到“月历视图”和“时间轴视图”。\n"
        "\n"
        "如何更新：\n"
        "  如果分享者后续只改了数据，一般只需同步 common.js 和 events_data.js\n"
        "  两个文件即可，不需要重新下载整个文件夹。\n"
        "\n"
        "---\n"
        "Beijing Major Events · Overview\n"
        "This folder is a self-contained static site.\n"
        "\n"
        "To view:\n"
        "  1. Save the whole folder locally (or keep it synced via OneDrive).\n"
        "  2. Double-click index.html to open in a browser.\n"
        "  3. Use the links inside to switch between overview, month and timeline views.\n"
        "\n"
        "Updates:\n"
        "  When the publisher updates the data, usually only common.js and events_data.js\n"
        "  change, so you do not need to re-download the whole folder.\n",
        encoding="utf-8",
    )

    # 清理 output 中不在白名单的残留文件（如改名前的旧数据文件、测试标记），
    # 保证分享包只含当前需要的文件；额外资源请放在 overrides/ 目录。
    for stale in out.iterdir():
        if stale.is_file() and stale.name not in output_files:
            stale.unlink()
            print(f"  清理残留: {stale.name}")

    print(f"\nPackaged {len(VIEWER_FILES)} files to {out}")
    for name in output_files:
        p = out / name
        size = p.stat().st_size
        print(f"  {name} ({size / 1024:.1f} KB)")
    print("\nNext: upload this folder to OneDrive and share the folder link.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
