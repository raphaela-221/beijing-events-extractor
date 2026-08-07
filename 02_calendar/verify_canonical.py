#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""canonical Events List.xlsx 结构守卫。

canonical 含手工 Excel 特性（Table2 表 A1:K、sharedStrings、printerSettings、
数据验证扩展）。openpyxl 的 load+save 会削掉 sharedStrings/printerSettings、
insert_cols 会破坏 table 列定义 -> Excel 修复框。本脚本检测这些损坏信号，
损坏则退出码 1（供 package_output.py 打包前拦截，坏文件永远 ship 不出去）。

用法：
  python3 verify_canonical.py                 # 检查默认 canonical
  python3 verify_canonical.py --excel path     # 检查指定 xlsx
  python3 verify_canonical.py --quiet          # 只在失败时输出
"""
import argparse
import sys
import zipfile
from pathlib import Path

# 复用 add_dates_column 的结构检测
sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_dates_column import verify_structure  # noqa: E402

CANONICAL = Path(__file__).resolve().parent.parent / "01_event_list_output" / "Events List.xlsx"

# 损坏信号阈值（基于已知好文件：15 part、sharedStrings 在、printerSettings 在、table ref A1:K）
EXPECTED_PARTS_MIN = 15  # 好文件 15 part；openpyxl 往返降到 12


def check(xlsx_path, quiet=False):
    s = verify_structure(xlsx_path)
    problems = []
    if s["parts"] < EXPECTED_PARTS_MIN:
        problems.append(f"parts={s['parts']} < {EXPECTED_PARTS_MIN}（openpyxl 往返会削 part）")
    if not s["has_sharedStrings"]:
        problems.append("sharedStrings.xml 缺失（openpyxl save 会把共享字符串转 inlineStr 并删此 part）")
    if not s["has_printerSettings"]:
        problems.append("printerSettings1.bin 缺失（openpyxl save 会删）")
    if not (s["table_ref"] or "").startswith("A1:K"):
        problems.append(f"table_ref={s['table_ref']!r} 不是 A1:K*（insert_cols 会错位 table 列定义）")

    ok = not problems
    if not quiet or not ok:
        print(f"检查: {xlsx_path}")
        print(f"  parts={s['parts']} sharedStrings={s['has_sharedStrings']} "
              f"printerSettings={s['has_printerSettings']} table_ref={s['table_ref']} "
              f"dimension={s['dimension']} r_cells={s['r_cells']}")
    if problems:
        print("  ❌ 损坏信号:")
        for p in problems:
            print(f"     - {p}")
        print("  >> canonical 已被 openpyxl 往返损坏，禁止发布。")
        print("     修复：用 02_calendar 的干净 base 重新铺底 + 重跑 enrich（XML 写，不 openpyxl save）。")
    else:
        if not quiet:
            print("  ✓ 结构完好")
    return ok


def main():
    ap = argparse.ArgumentParser(description="canonical xlsx 结构守卫：检测 openpyxl 往返损坏。")
    ap.add_argument("--excel", default=str(CANONICAL), help=f"xlsx 路径（默认 canonical）")
    ap.add_argument("--quiet", action="store_true", help="只在失败时输出")
    args = ap.parse_args()
    p = Path(args.excel)
    if not p.exists():
        print(f"ERROR: {p} 不存在", file=sys.stderr)
        return 2
    return 0 if check(p, quiet=args.quiet) else 1


if __name__ == "__main__":
    raise SystemExit(main())
