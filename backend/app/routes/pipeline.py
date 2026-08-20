"""流程健康检查 + 下一步建议（指南 §5.4）。

8 个检查：env_keys / canonical_exists / canonical_structure / dates_pending /
data_freshness / changed_months / concert_state / disk_space。
下一步建议按「阻断级优先、其次警告级、按检查顺序」取第一条命中。
stats（事件总数/High/覆盖月份/最后修改）和 dates_pending 合并在一次 openpyxl read_only 里算。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime

from fastapi import APIRouter, Request

from .. import config
from ..auth import require_user

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

_CONCERT_RE = re.compile(r"演唱会|音乐节|巡演|concert|演出", re.IGNORECASE)
_DISK_LOW = 500 * 1024 * 1024  # 500MB
_CONCERT_STALE_DAYS = 30


def compute_state() -> dict:
    """跑 8 项健康检查，返回 {checks, next_action, stats}。纯函数，供 route 与 maintenance.selfcheck 复用。"""
    # 1 env_keys
    ds = os.getenv("OPENAI_API_KEY", "").strip()
    ark = os.getenv("ARK_API_KEY", "").strip()
    has_key = bool(ds or ark)
    checks = [_check("env_keys", "block" if not has_key else "ok",
                     "DeepSeek/Ark key 已配置" if has_key else "未配置 DeepSeek/Ark key，抽取类操作将禁用",
                     not has_key)]

    # 2 canonical_exists
    exists = config.CANONICAL_PATH.exists()
    checks.append(_check("canonical_exists", "block" if not exists else "ok",
                         "Events List.xlsx 存在" if exists else "Events List.xlsx 不存在，请用源 Excel 铺底",
                         not exists))

    # 3 canonical_structure（跑 verify_canonical.py）
    code = _verify_canonical()
    struct_detail = {0: "结构完好", 1: "canonical 结构损坏，发布已阻断", 2: "canonical 文件不存在"}.get(code, "未知")
    checks.append(_check("canonical_structure", "block" if code != 0 else "ok",
                         struct_detail, code != 0))

    # stats + dates_pending（一次 read_only）
    stats, dates_pending = (_read_canonical_stats() if exists else ({}, 0))

    # 4 dates_pending
    checks.append(_check("dates_pending", "warn" if dates_pending > 0 else "ok",
                         f"{dates_pending} 条演唱会待补 Dates" if dates_pending else "所有演唱会 Dates 已补",
                         False))

    # 5 data_freshness
    ed = config.CALENDAR_DIR / "events_data.js"
    stale = exists and ed.exists() and config.CANONICAL_PATH.stat().st_mtime > ed.stat().st_mtime
    checks.append(_check("data_freshness", "warn" if stale else "ok",
                         "canonical 已更新，日历数据待重跑" if stale else "日历数据已是最新",
                         False))

    # 6 changed_months
    cm = _read_changed_months()
    checks.append(_check("changed_months", "warn" if cm else "ok",
                         f"{len(cm)} 个月待重算主题：{', '.join(cm)}" if cm else "无待重算月份",
                         False))

    # 7 concert_state
    days = _concert_stale_days()
    concert_stale = days is not None and days > _CONCERT_STALE_DAYS
    checks.append(_check("concert_state", "warn" if concert_stale else "ok",
                         f"上次采集 {days} 天前，建议重跑" if concert_stale else "演唱会采集近期已跑",
                         False))

    # 8 disk_space
    free = shutil.disk_usage(config.DATA_DIR).free
    low = free < _DISK_LOW
    checks.append(_check("disk_space", "warn" if low else "ok",
                         f"可用 {free // (1024 * 1024)} MB" + ("，空间不足" if low else ""),
                         False))

    return {
        "checks": checks,
        "next_action": _next_action(checks),
        "stats": stats,
    }


@router.get("/state")
def get_state(request: Request):
    require_user(request)
    return compute_state()


def _check(cid: str, status: str, detail: str, block: bool) -> dict:
    return {"id": cid, "status": status, "detail": detail, "block": block}


def _verify_canonical() -> int:
    """跑 verify_canonical.py --quiet。0=完好 1=损坏 2=不存在。"""
    script = config.CALENDAR_DIR / "verify_canonical.py"
    if not script.exists():
        return 2
    try:
        r = subprocess.run(
            [sys.executable, str(script), "--quiet"],
            capture_output=True, timeout=30,
        )
        return r.returncode
    except Exception:
        return 1


def _read_canonical_stats() -> tuple[dict, int]:
    """一次 read_only 读 canonical：算 total/high/covered_months/last_modified + dates_pending。
    read_only=True 绝不 save（canonical 含手工特性，save 会损坏）。"""
    import openpyxl

    wb = openpyxl.load_workbook(str(config.CANONICAL_PATH), read_only=True)
    ws = wb.active
    total = 0
    high = 0
    months: set[str] = set()
    dates_pending = 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or r[0] is None:
            continue
        total += 1
        # Priority = col 5 (F)
        if r[5] and str(r[5]).strip().lower() == "high":
            high += 1
        # Start Date = col 3 (D) -> YYYY-MM
        sd = r[3]
        if sd:
            s = str(sd)[:7]
            if len(s) == 7 and s[4] == "-":
                months.add(s)
        # dates_pending: Dates col 17 (R) 为空 + 演唱会类
        dates_val = r[17] if len(r) > 17 else None
        if not dates_val or not str(dates_val).strip():
            topic = " ".join(str(r[i] or "") for i in (1, 8, 9))  # Topic + Desc + Headline
            if _CONCERT_RE.search(topic):
                dates_pending += 1
    wb.close()
    mtime = datetime.fromtimestamp(config.CANONICAL_PATH.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return (
        {
            "total_events": total,
            "high_priority": high,
            "covered_months": len(months),
            "last_modified": mtime,
        },
        dates_pending,
    )


def _read_changed_months() -> list[str]:
    p = config.CALENDAR_DIR / "state" / "last_run.json"
    if not p.exists():
        return []
    try:
        return json.load(open(p, encoding="utf-8")).get("changed_months") or []
    except Exception:
        return []


def _concert_stale_days() -> int | None:
    p = config.STEP1_MAIN.parent / "state" / "concert_scrape_state.json"
    if not p.exists():
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
        last = d.get("last_scrape_date")
        if not last:
            return None
        return (date.today() - date.fromisoformat(last)).days
    except Exception:
        return None


def _next_action(checks: list[dict]) -> dict | None:
    # 阻断级优先，其次警告级，按 checks 顺序取第一条命中
    for c in checks:
        if c["block"]:
            return _action_for(c)
    for c in checks:
        if c["status"] == "warn":
            return _action_for(c)
    return None


# 每个检查的下一步建议文案 + 直达链接
_ACTION_MAP = {
    "env_keys": ("配置 LLM API key", "在 .env 配置 DeepSeek 或 Ark key 后才能跑抽取类操作", "/settings", "block"),
    "canonical_exists": ("初始化人工审核清单", "用源 Excel 铺底生成 Events List.xlsx", "/review", "block"),
    "canonical_structure": ("修复 canonical 结构", "canonical 结构损坏，发布已阻断，请用 .bak 恢复或重新生成", "/review", "block"),
    "dates_pending": ("补全演唱会 Dates", "有演唱会待补离散日期，建议先跑 Dates 自动抽取", "/review", "warn"),
    "data_freshness": ("重跑日历抽取", "canonical 已更新，日历数据待重新抽取", "/step2", "warn"),
    "changed_months": ("生成月度主题", "有月份待重算月度主题", "/step2", "warn"),
    "concert_state": ("采集演唱会", "演唱会数据已超 30 天未采集", "/step1", "warn"),
    "disk_space": ("腾出磁盘空间", "data/ 可用空间不足，建议清理旧运行记录", "/runs", "warn"),
}


def _action_for(c: dict) -> dict:
    title, desc, link, sev = _ACTION_MAP.get(c["id"], (c["detail"], "", "/", "warn"))
    return {"id": c["id"], "title": title, "desc": desc, "link": link, "severity": sev}
