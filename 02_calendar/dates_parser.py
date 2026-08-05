#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离散日期解析器：把 canonical Excel `Dates` 列的友好格式展开成 YYYY-MM-DD 列表。

支持格式（同一段文本内可混用，逗号 / 顿号 / 分号 / 中文逗号均可作分隔）：
  - 8.14-16, 8.19, 8.21-23, 8.28-30        # 同年同月省略，- 或 ~ 表连续段
  - 2026-08-14~2026-08-16, 2026-08-19      # 跨年月完整明写
  - 2026-08-14,2026-08-15,2026-08-16       # 枚举单日
  - 8月14日至16日, 8月19日                  # 中文写法

缺年份 / 月份时用 fallback_year / fallback_month（通常取自该事件的 Start Date）。
解析失败返回 []，调用方回退到 start/end 连续区间模型。
"""
import re
from datetime import date, timedelta


def parse_dates_field(raw, fallback_year=None, fallback_month=None):
    """展开 Dates 列原文为排序去重的 YYYY-MM-DD 列表。

    Args:
        raw: Dates 列原文（str 或 None）
        fallback_year: int，省略年份时用（如 2026）
        fallback_month: int，省略月份时用（如 8）

    Returns:
        list[str]，形如 ["2026-08-14", "2026-08-15", ...]；空输入返回 []
    """
    if raw is None or not str(raw).strip():
        return []
    s = str(raw).strip()
    # 统一分隔符 -> 逗号
    s = re.sub(r"[，、;；]", ",", s)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        return []

    results = set()
    for part in parts:
        results.update(_parse_part(part, fallback_year, fallback_month))
    return sorted(results)


def _parse_part(part, fy, fm):
    """解析单个片段（单日或连续段）。"""
    # 完整段：2026-08-14~2026-08-16 / 2026-08-14 至 2026-08-16
    m = re.match(
        r"^(\d{4})-(\d{1,2})-(\d{1,2})\s*[-~至到]\s*(\d{4})-(\d{1,2})-(\d{1,2})$",
        part,
    )
    if m:
        return _expand_range(
            int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6])
        )

    # 完整单日：2026-08-14
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", part)
    if m:
        d = _fmt(int(m[1]), int(m[2]), int(m[3]))
        return [d] if d else []

    # 省略段：8.14-16 / 8.14~16 / 8.14-8.16
    m = re.match(
        r"^(\d{1,2})\.(\d{1,2})\s*[-~至到]\s*(\d{1,2})(?:\.(\d{1,2}))?$", part
    )
    if m:
        y = fy
        m1, d1 = int(m[1]), int(m[2])
        if m[4]:  # 8.14-8.16 -> end 月=group3, 日=group4
            m2, d2 = int(m[3]), int(m[4])
        else:  # 8.14-16 -> end 月=m1, 日=group3
            m2, d2 = m1, int(m[3])
        if y is None:
            return []
        return _expand_range(y, m1, d1, y, m2, d2)

    # 省略单日：8.14
    m = re.match(r"^(\d{1,2})\.(\d{1,2})$", part)
    if m:
        y = fy
        if y is None:
            return []
        d = _fmt(y, int(m[1]), int(m[2]))
        return [d] if d else []

    # 中文段：8月14日至16日
    m = re.match(r"^(\d{1,2})月(\d{1,2})日\s*[至到\-~]\s*(\d{1,2})日$", part)
    if m:
        y = fy
        if y is None:
            return []
        return _expand_range(y, int(m[1]), int(m[2]), y, int(m[1]), int(m[3]))

    # 中文单日：8月14日
    m = re.match(r"^(\d{1,2})月(\d{1,2})日$", part)
    if m:
        y = fy
        if y is None:
            return []
        d = _fmt(y, int(m[1]), int(m[2]))
        return [d] if d else []

    return []


def _expand_range(y1, m1, d1, y2, m2, d2):
    """展开 [start, end] 闭区间为 YYYY-MM-DD 列表。"""
    try:
        start = date(y1, m1, d1)
        end = date(y2, m2, d2)
    except ValueError:
        return []
    if end < start:
        start, end = end, start
    out, cur = [], start
    while cur <= end:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


def _fmt(y, m, d):
    try:
        return date(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


if __name__ == "__main__":
    # 汪苏泷用例：8.14-16、19、21-23、28-30 = 10 场
    ws = parse_dates_field("8.14-16, 8.19, 8.21-23, 8.28-30", 2026, 8)
    assert len(ws) == 10, f"expected 10, got {len(ws)}: {ws}"
    assert ws[0] == "2026-08-14" and ws[-1] == "2026-08-30", ws
    assert "2026-08-17" not in ws and "2026-08-20" not in ws, ws
    print("✓ 汪苏泷 8.14-16/19/21-23/28-30 -> 10 场")

    # 完整明写
    full = parse_dates_field("2026-08-14~2026-08-16, 2026-08-19", 2026, 8)
    assert full == ["2026-08-14", "2026-08-15", "2026-08-16", "2026-08-19"], full
    print("✓ 完整明写 2026-08-14~16, 19 -> 4 天")

    # 枚举
    enum = parse_dates_field("2026-08-14,2026-08-15", 2026, 8)
    assert enum == ["2026-08-14", "2026-08-15"], enum
    print("✓ 枚举 2 天")

    # 中文
    cn = parse_dates_field("8月14日至16日, 8月19日", 2026, 8)
    assert cn == ["2026-08-14", "2026-08-15", "2026-08-16", "2026-08-19"], cn
    print("✓ 中文 8月14日至16日、19日 -> 4 天")

    # 空输入
    assert parse_dates_field("", 2026, 8) == []
    assert parse_dates_field(None, 2026, 8) == []
    print("✓ 空输入回退 []")

    # 跨月段：8.30-9.2
    cross = parse_dates_field("8.30-9.2", 2026, 8)
    assert cross == ["2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02"], cross
    print("✓ 跨月段 8.30-9.2 -> 4 天")

    print("\n所有 dates_parser 单测通过。")
