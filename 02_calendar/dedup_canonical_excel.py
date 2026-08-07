#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deduplicate the canonical Events List.xlsx in place (with .bak backup).

This is the Excel-layer dedup: it runs directly on the canonical
`01_event_list_output/Events List.xlsx` (the single source of truth) and
catches duplicates regardless of how they entered -- extraction, manual paste,
or import. The extraction-time dedup in 01_event_extractor only sees one batch
at a time, so cross-run / cross-source dups slip through and accumulate here.

Uses the SAME key logic as the extractor (src/dedup_key.py) so behavior is
consistent across all three layers (extraction, Excel, calendar display).

Policy:
  - 中小学春秋假 / 中小学寒暑假 duplicates are AUTO-REMOVED (high confidence: same city +
    same vacation type + same year = definitely the same event). Within each
    group the most specific row is kept (headline that names the city, keywords
    with a day count).
  - Other-category duplicate groups are REPORTED ONLY (same city+date+topic
    could still be distinct events; leave the decision to a human).

Usage:
    python3 dedup_canonical_excel.py            # report + auto-remove vacation dups, .bak backup
    python3 dedup_canonical_excel.py --dry-run  # report only, no write
    python3 dedup_canonical_excel.py --source /path/to/other.xlsx
"""
import argparse
import shutil
import sys
from pathlib import Path

from openpyxl import load_workbook

# Import the shared leaf module (no heavy deps) from the extractor package.
sys.path.insert(0, str(Path(__file__).parent.parent / "01_event_extractor"))
from src.dedup_key import deduplicate_events, group_duplicates, _has_identity  # noqa: E402

CANON = Path(__file__).parent.parent / "01_event_list_output" / "Events List.xlsx"
SHEET = "Events List"
COLUMNS = [
    "No.", "Topic", "Link", "Start Date", "End Date", "Priority",
    "Event Keywords", "Event English Keywords", "Event Description",
    "Headline", "备注",
]
VACATION_CATEGORIES = ("中小学春秋假", "中小学寒暑假")


def parse_args():
    p = argparse.ArgumentParser(description="Deduplicate the canonical Events List.xlsx.")
    p.add_argument("--source", default=str(CANON), help="Path to the Excel file (default: canonical).")
    p.add_argument("--dry-run", action="store_true", help="Report only; do not write or back up.")
    p.add_argument("--prune-malformed", action="store_true",
                    help="Also delete malformed rows (only Link, no headline/dates/topic).")
    return p.parse_args()


def load_events(ws):
    """Read all non-blank data rows into event dicts tagged with their sheet row."""
    rows = ws.iter_rows(min_row=1, values_only=True)
    header = [str(c).strip() if c is not None else "" for c in next(rows)]
    idx = {name: i for i, name in enumerate(header)}

    events = []
    for row_num, row in enumerate(rows, start=2):  # row 1 was header
        if all(c is None or c == "" for c in row):
            continue
        ev = {"_sheet_row": row_num}
        for col in COLUMNS:
            i = idx.get(col)
            ev[col] = (row[i] if i is not None and i < len(row) else None)
        events.append(ev)
    return events, idx


def fmt(ev, width=30):
    hl = str(ev.get("Headline") or "").strip()
    no = ev.get("No.")
    no_s = str(no) if no is not None else "?"
    start = str(ev.get("Start Date") or "")[:10] or "?"
    return f"No.{no_s:<5} {start}  {hl[:width]}"


def main():
    args = parse_args()
    src_path = Path(args.source)
    if not src_path.exists():
        raise FileNotFoundError(f"Excel not found: {src_path}")

    # ⚠️ 危险：本脚本 wb.save(src_path) 会 openpyxl 往返 canonical，损坏手工 Excel
    # 特性（削 sharedStrings/printerSettings、删数据验证扩展、可能错位 table 列定义
    # -> Excel 修复框）。canonical 含 Table2 表 + 手工数据验证，openpyxl 保不住。
    # 跑完后必须用 verify_canonical.py 检查 + 重铺 canonical（02_calendar 干净 base
    # + 重跑 enrich XML 写），否则 canonical 带病、package 守卫会拦截。
    # 长期方案：dedup 改成直接 XML 删行（不 openpyxl save），暂未实现。
    print("⚠️  警告：dedup 用 openpyxl save canonical，会损坏文件结构（见上）。")
    print("    跑完务必 verify_canonical.py 检查 + 重铺 canonical。建议改用 XML 方式或先备份。")
    if not args.dry_run:
        print("    （--dry-run 不写盘，无此风险）")
    print()

    wb = load_workbook(src_path)
    if SHEET not in wb.sheetnames:
        raise ValueError(f"'{src_path}' has no sheet named '{SHEET}'. Sheets: {wb.sheetnames}")
    ws = wb[SHEET]

    events, _ = load_events(ws)
    print(f"Loaded {len(events)} events from {src_path}")
    malformed = [e for e in events if not _has_identity(e)]
    if malformed:
        print(f"⚠️  {len(malformed)} 行残缺（仅有Link等，无标题/日期/分类）-- 不参与去重，建议人工删除：")
        for e in malformed:
            print(f"    sheet行{e['_sheet_row']} Link={str(e.get('Link') or '')[:50]}")

    # --- Deduplicate ALL categories ---
    # Vacation: same city + vacation-type + year = one event.
    # Other: same headline + same dates = one event (same headline on different
    # dates = different days; same date different headline = different events).
    kept, removed = deduplicate_events(events)
    n_mal = len(malformed) if args.prune_malformed else 0
    if args.prune_malformed and malformed:
        removed = removed + malformed
        kept = [e for e in kept if _has_identity(e)]
    all_groups = group_duplicates(events)
    rm_ids = {id(m) for m in removed}

    print("\n" + "=" * 70)
    print(f"重复组（将自动去重）：{len(all_groups)} 组")
    print("=" * 70)
    for key, members in all_groups:
        kept_member = next((m for m in members if id(m) not in rm_ids), members[0])
        print(f"\n  key: {key}")
        print(f"  ✓ 保留 {fmt(kept_member)}")
        for m in members:
            if id(m) in rm_ids:
                print(f"  ✗ 删除 {fmt(m)}")

    print("\n" + "-" * 70)
    n_dup = len(removed) - n_mal
    extra = f" + {n_mal} 条残缺" if n_mal else ""
    print(f"汇总：{len(events)} 条 -> {len(kept)} 条（删除 {n_dup} 条重复{extra}）")

    if args.dry_run:
        print("\n[--dry-run] 未写入文件。")
        return 0

    if not removed:
        print("\n无重复/残缺需删除，未写入文件。")
        return 0

    # --- Backup, delete rows bottom-up, renumber No., save ---
    bak = src_path.with_suffix(src_path.suffix + ".bak")
    shutil.copy2(src_path, bak)
    print(f"\n已备份: {bak}")

    rows_to_delete = sorted((ev["_sheet_row"] for ev in removed), reverse=True)
    for r in rows_to_delete:
        ws.delete_rows(r, 1)

    # Renumber No. column (col A) for remaining data rows.
    n = 0
    for row in ws.iter_rows(min_row=2, values_only=False):
        # a data row if any cell in the main columns is non-empty
        if all(c.value is None or c.value == "" for c in row[:11]):
            continue
        n += 1
        row[0].value = n

    wb.save(src_path)
    print(f"已写入: {src_path}")
    print(f"删除 {len(removed)} 行，重新编号 {n} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
