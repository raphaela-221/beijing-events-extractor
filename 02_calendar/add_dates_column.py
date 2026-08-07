#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""零损耗给 Events List.xlsx 加 Dates 列（写到 R 列，表格范围外）。

为什么不用 openpyxl save：canonical 含手工 Excel 特性（Table2 表 A1:K、
sharedStrings、printerSettings、数据验证扩展），openpyxl 的 load+save 会：
  - 把 sharedStrings 全转 inlineStr、删掉 xl/sharedStrings.xml
  - 删 printerSettings1.bin、数据验证扩展
  - insert_cols 不更新 table1.xml -> 表头与列错位 -> Excel 修复框
本模块直接改 xl/worksheets/sheet1.xml，只加 R 列单元格 + 更新 dimension，
其余 part 字节不动，table/sharedStrings/printerSettings/数据验证全保留。

R 列（第 18 列）选择依据：table 范围 A1:K（11 列），L-Q 已有零散数据
（L 260 个带值单元格），R 列零单元格，零冲突。

用法：
  from add_dates_column import write_dates, verify_structure
  write_dates("Events List.xlsx", {1: "Dates", 940: "8.14-16, 8.19, ..."})

  # CLI（单行补数据）：
  python3 add_dates_column.py --excel path --row 940 --value "8.14-16, 8.19"

  # 自检（写到副本，验证结构）：
  python3 add_dates_column.py --self-test --excel path
"""
import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

DATES_COL = "R"            # 第 18 列，表外
DATES_HEADER = "Dates"
SHEET1 = "xl/worksheets/sheet1.xml"


def _xml_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _col_to_num(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def _cell_xml(row: int, value: str) -> str:
    """R{row} 的 inlineStr 单元格（不依赖 sharedStrings）。"""
    return f'<c r="{DATES_COL}{row}" t="inlineStr"><is><t>{_xml_escape(value)}</t></is></c>'


def _remove_existing_r_cell(xml: str, row: int) -> str:
    """删除该行已有的 R 单元格（自闭合或带内容），实现幂等。"""
    rn = str(row)
    # 自闭合：<c r="R940" s="9"/>
    xml = re.sub(r'<c r="' + DATES_COL + rn + r'"[^>]*?/>', "", xml)
    # 带内容：<c r="R940" t="inlineStr"><is>...</is></c>
    xml = re.sub(r'<c r="' + DATES_COL + rn + r'"[^>]*>.*?</c>', "", xml, flags=re.S)
    return xml


def _insert_r_cell(xml: str, row: int, cell_xml: str) -> str:
    """在该行 </row> 前插入 R 单元格。"""
    rn = str(row)
    row_pat = re.compile(r'(<row r="' + rn + r'"[^>]*>)(.*?)(</row>)', flags=re.S)
    m = row_pat.search(xml)
    if not m:
        raise ValueError(f"row {row} 在 sheet1.xml 中未找到")
    return xml[: m.end(2)] + cell_xml + xml[m.start(3) :]


def _bump_dimension(xml: str, target_col: str = DATES_COL) -> str:
    """dimension 末列不够 target_col 则提升（A1:Q1573 -> A1:R1573）。"""
    m = re.search(r'<dimension ref="A1:([A-Z]+)(\d+)"/>', xml)
    if not m:
        return xml
    end_col, end_row = m.group(1), int(m.group(2))
    if _col_to_num(end_col) < _col_to_num(target_col):
        end_col = target_col
    new_dim = f'<dimension ref="A1:{end_col}{end_row}"/>'
    return re.sub(r'<dimension ref="A1:[A-Z]+\d+"/>', new_dim, xml)


def write_dates(xlsx_path, row_dates: dict) -> int:
    """把 {row_num: dates_str} 写到 xlsx 的 R 列。返回写入单元格数。

    幂等：同一行重复写会替换。保留所有原有 part 字节不动（除 sheet1.xml）。
    row_dates 应包含 {1: "Dates"} 作为表头。
    """
    xlsx_path = Path(xlsx_path)
    if not row_dates:
        return 0

    with zipfile.ZipFile(xlsx_path) as zin:
        sheet1_xml = zin.read(SHEET1).decode("utf-8")

    for row in sorted(row_dates.keys()):
        cell = _cell_xml(row, str(row_dates[row]))
        sheet1_xml = _remove_existing_r_cell(sheet1_xml, row)
        sheet1_xml = _insert_r_cell(sheet1_xml, row, cell)

    sheet1_xml = _bump_dimension(sheet1_xml, DATES_COL)

    # 重写 zip：sheet1.xml 用新内容，其余 part 原样（ZipInfo 保留 compress_type）
    tmp = xlsx_path.with_suffix(xlsx_path.suffix + ".tmp")
    with zipfile.ZipFile(xlsx_path) as zin, zipfile.ZipFile(tmp, "w") as zout:
        for info in zin.infolist():
            if info.filename == SHEET1:
                zout.writestr(info, sheet1_xml.encode("utf-8"))
            else:
                zout.writestr(info, zin.read(info.filename))
    tmp.replace(xlsx_path)
    return len(row_dates)


def verify_structure(xlsx_path) -> dict:
    """结构自检：返回各关键指标 dict。供 verify_canonical / 测试用。"""
    xlsx_path = Path(xlsx_path)
    z = zipfile.ZipFile(xlsx_path)
    names = z.namelist()
    sheet1 = z.read(SHEET1).decode("utf-8", "replace")
    r_cells = len(re.findall(r'<c r="' + DATES_COL + r'\d+"', sheet1))
    dim = re.search(r'<dimension ref="(A1:[A-Z]+\d+)"/>', sheet1)
    has_shared = "xl/sharedStrings.xml" in names
    has_printer = "xl/printerSettings/printerSettings1.bin" in names
    # table ref
    table_xml = z.read("xl/tables/table1.xml").decode("utf-8", "replace")
    table_ref = re.search(r'<table[^>]*ref="([^"]+)"', table_xml)
    return {
        "parts": len(names),
        "has_sharedStrings": has_shared,
        "has_printerSettings": has_printer,
        "table_ref": table_ref.group(1) if table_ref else None,
        "dimension": dim.group(1) if dim else None,
        "r_cells": r_cells,
    }


def _self_test(xlsx_path) -> int:
    """写到副本，验证结构没坏。返回 0 通过，1 失败。"""
    import tempfile
    src = Path(xlsx_path)
    tmp = Path(tempfile.mktemp(suffix="_selftest.xlsx"))
    shutil.copy2(src, tmp)
    before = verify_structure(tmp)
    write_dates(tmp, {1: DATES_HEADER, 940: "8.14-16, 8.19, 8.21-23, 8.28-30"})
    after = verify_structure(tmp)
    print("=== self-test ===")
    print("before:", before)
    print("after :", after)
    ok = (
        after["parts"] == before["parts"]
        and after["has_sharedStrings"]
        and after["has_printerSettings"]
        and after["table_ref"] == "A1:K1573"
        and after["dimension"] == "A1:R1573"
        and after["r_cells"] == 2  # header + 1 data
    )
    # 抽查值
    from openpyxl import load_workbook
    wb = load_workbook(tmp, read_only=True, data_only=True)
    ws = wb["Events List"]
    hdr = [c.value for c in ws[1]]
    dates_idx = hdr.index("Dates") + 1 if "Dates" in hdr else None
    val940 = ws.cell(row=940, column=dates_idx).value if dates_idx else None
    wb.close()
    print(f"  R1 header = {hdr[dates_idx-1] if dates_idx else None!r}")
    print(f"  R940 value = {val940!r}")
    ok = ok and val940 == "8.14-16, 8.19, 8.21-23, 8.28-30"
    print("RESULT:", "PASS" if ok else "FAIL")
    tmp.unlink(missing_ok=True)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="零损耗给 Events List.xlsx 加 Dates 列（R 列，表外）。")
    ap.add_argument("--excel", required=True, help="xlsx 路径")
    ap.add_argument("--row", type=int, help="要写的行号")
    ap.add_argument("--value", help="Dates 值（如 8.14-16, 8.19）")
    ap.add_argument("--self-test", action="store_true", help="写到副本验证结构")
    args = ap.parse_args()

    if args.self_test:
        return _self_test(args.excel)
    if not (args.row and args.value is not None):
        ap.error("--row 和 --value 必须一起给（或用 --self-test）")
    n = write_dates(args.excel, {args.row: args.value})
    print(f"wrote {n} cell(s) to column {DATES_COL} of {args.excel}")
    s = verify_structure(args.excel)
    print("structure:", s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
