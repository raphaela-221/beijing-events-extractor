#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enrich canonical Events List.xlsx：LLM 从 Event Description 抽离散场次日期写回 Dates 列。

幂等：已有 Dates 的行跳过；Dates 列不存在则在 End Date 后插入。
只处理含演唱会/音乐节/演出/巡演 且 description 有日期线索 的行。
抽取结果用 parse_dates_field 校验，解析失败则跳过（不污染数据）。

用法：
  python3 enrich_concert_dates.py            # 写回 canonical
  python3 enrich_concert_dates.py --dry-run   # 只打印不写
  python3 enrich_concert_dates.py --excel /path/to/other.xlsx
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent  # 项目根
CANONICAL = ROOT / "01_event_list_output" / "Events List.xlsx"

# 先加载 .env（src 模块 import 时读 env var），再 import src
load_dotenv(dotenv_path=ROOT / ".env")

# dates_parser 在 02_calendar/
sys.path.insert(0, str(ROOT / "02_calendar"))
from dates_parser import parse_dates_field  # noqa: E402

# llm_client 在本目录 src/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.llm_client import call_llm, get_llm_model, print_usage_summary  # noqa: E402


SYSTEM_PROMPT = """你是演出日期抽取助手。从中文演出描述里抽取每一场演出的具体日期，输出 Dates 列格式。

输出格式（严格遵守）：
- 逗号分隔，每段都带月份：8.14-16, 8.19, 8.21-23, 8.28-30
- 连续段用 - 连首尾日：8.14-16 = 14/15/16 三天
- 单日：8.19
- 跨年月用完整明写：2026-08-30~2026-09-02
- 只输出日期段，不要解释、引号、代码块或多余文字
- 年份从描述取；同年同月每段都重复月份（便于回解析）

示例：
描述："演唱会将于2026年8月14日至16日、8月19日、8月21日至23日、8月28日至30日举办"
输出：8.14-16, 8.19, 8.21-23, 8.28-30

描述："演出定于2026年9月10日、11日、13日"
输出：9.10-11, 9.13

描述："2026年8月30日至9月2日连续"
输出：2026-08-30~2026-09-02
"""

DATE_HINT = re.compile(
    r"\d{1,2}月\d{1,2}日|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\.\d{1,2}|至|到"
)
CONCERT_HINT = re.compile(r"演唱会|音乐节|巡演|concert|演出")


def _ensure_dates_col(ws):
    """确保 Events List sheet 有 Dates 列，返回 1-based 列号。"""
    header = [str(c.value).strip() if c.value else "" for c in ws[1]]
    if "Dates" in header:
        return header.index("Dates") + 1
    if "End Date" not in header:
        raise ValueError("Events List 表头缺 End Date 列，无法定位 Dates 插入位置")
    end_idx = header.index("End Date") + 1  # 1-based
    ws.insert_cols(end_idx + 1)
    ws.cell(row=1, column=end_idx + 1, value="Dates")
    print(f"  插入 Dates 列于第 {end_idx + 1} 列（End Date 后）")
    return end_idx + 1


def _compress(dates_list):
    """['2026-08-14',...] -> '8.14-16, 8.19, 8.21-23, 8.28-30'（每段带月，可读+可回解析）。"""
    parsed = []
    for s in sorted(set(dates_list)):
        y, m, d = s.split("-")
        parsed.append((int(y), int(m), int(d)))
    groups, cur = [], None
    for y, m, d in parsed:
        if cur and cur[0] == y and cur[1] == m:
            cur[2].append(d)
        else:
            cur = (y, m, [d])
            groups.append(cur)
    parts = []
    for _y, m, days in groups:
        days.sort()
        segs, ss, prev = [], days[0], days[0]
        for d in days[1:]:
            if d == prev + 1:
                prev = d
                continue
            segs.append((ss, prev))
            ss = prev = d
        segs.append((ss, prev))
        for a, b in segs:
            parts.append(f"{m}.{a}" if a == b else f"{m}.{a}-{b}")
    return ", ".join(parts)


def _parse_llm_output(raw):
    s = (raw or "").strip().strip("`").strip('"').strip("'").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return s


def enrich(excel_path, dry_run=False):
    wb = load_workbook(excel_path)
    if "Events List" not in wb.sheetnames:
        raise ValueError(f"{excel_path} 无 'Events List' sheet")
    ws = wb["Events List"]

    dates_col = _ensure_dates_col(ws)
    header = [str(c.value).strip() if c.value else "" for c in ws[1]]
    col = {n: i + 1 for i, n in enumerate(header)}  # 1-based

    enriched, skipped_has_dates, skipped_no_concert, failed = 0, 0, 0, 0
    for r in range(2, ws.max_row + 1):
        dates_val = ws.cell(row=r, column=dates_col).value
        if dates_val and str(dates_val).strip():
            skipped_has_dates += 1
            continue

        topic = str(ws.cell(row=r, column=col.get("Topic", 0)).value or "")
        desc = str(ws.cell(row=r, column=col.get("Event Description", 0)).value or "")
        if not (CONCERT_HINT.search(topic) or CONCERT_HINT.search(desc)):
            skipped_no_concert += 1
            continue
        if not DATE_HINT.search(desc):
            continue

        # fallback 年/月从 Start Date 取
        sd = ws.cell(row=r, column=col.get("Start Date", 0)).value
        start_str = sd.strftime("%Y-%m-%d") if isinstance(sd, datetime) else (str(sd) if sd else None)
        fy = fm = None
        if start_str:
            try:
                p = str(start_str).replace("/", "-").split("-")
                fy, fm = int(p[0]), int(p[1])
            except (ValueError, IndexError):
                pass

        try:
            resp = call_llm(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"描述：{desc}\n输出："},
                ],
                model=get_llm_model(),
                temperature=0.0,
                max_completion_tokens=512,
            )
            content = _parse_llm_output(resp.choices[0].message.content)
        except Exception as e:
            print(f"  ⚠️ LLM 调用失败 row {r}: {e}")
            failed += 1
            continue

        dates_list = parse_dates_field(content, fy, fm)
        if not dates_list:
            print(f"  ⚠️ 抽取为空 row {r}: desc={desc[:30]!r} -> LLM: {content[:60]!r}")
            failed += 1
            continue

        dates_str = _compress(dates_list)
        if not dry_run:
            ws.cell(row=r, column=dates_col, value=dates_str)
        print(f"  ✓ row {r}: {dates_str}   ({desc[:30]}...)")
        enriched += 1

    if not dry_run and enriched:
        wb.save(excel_path)
        print(f"\n已写回 {excel_path}")

    print(
        f"\n[Enrich] enriched={enriched}  "
        f"skipped(已有Dates)={skipped_has_dates}  "
        f"skipped(非演唱会)={skipped_no_concert}  "
        f"failed={failed}  dry_run={dry_run}"
    )
    print_usage_summary()
    return enriched


def main():
    ap = argparse.ArgumentParser(description="LLM 从 Event Description 抽离散场次日期写回 Dates 列。")
    ap.add_argument("--excel", default=str(CANONICAL), help=f"Excel 路径（默认 canonical：{CANONICAL}）")
    ap.add_argument("--dry-run", action="store_true", help="只打印不写回")
    args = ap.parse_args()

    p = Path(args.excel)
    if not p.exists():
        print(f"ERROR: {p} 不存在")
        return 1
    print(f"Enriching: {p}  (dry_run={args.dry_run})\n")
    enrich(p, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
