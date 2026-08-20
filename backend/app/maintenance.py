"""后台维护：自检 + 自动清理。

自检复用 pipeline.compute_state 的 8 项检查 + data 目录统计。
自动清理：回收站超 retention purge / .bak 超份数删旧 / 孤儿 run 目录清理。
.bak 永不因 run 清理而删（唯一回滚绳，只按份数淘汰）。
历史写 data/cleanup_log.jsonl；最近摘要写 settings.json 的 last_selfcheck/last_cleanup。
"""
from __future__ import annotations

import json
import os
import shutil
import socket
from datetime import datetime
from pathlib import Path

from . import config, db, settings_store
from .routes import pipeline as pipeline_mod
from .runs import store

CLEANUP_LOG = config.DATA_DIR / "cleanup_log.jsonl"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _dir_size(p: Path) -> int:
    if not p.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def _data_stats() -> dict:
    """data 目录统计，供设置页与自检展示。"""
    conn = db.connect()
    try:
        runs_count = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE deleted_at IS NULL"
        ).fetchone()[0]
        trash_count = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE deleted_at IS NOT NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    bak_dir = config.CANONICAL_BACKUPS_DIR
    baks = sorted(bak_dir.glob("*.bak.xlsx")) if bak_dir.exists() else []
    db_size = config.DB_PATH.stat().st_size if config.DB_PATH.exists() else 0
    free = shutil.disk_usage(config.DATA_DIR).free
    return {
        "runs_count": runs_count,
        "trash_count": trash_count,
        "bak_count": len(baks),
        "data_size": _dir_size(config.DATA_DIR),
        "db_size": db_size,
        "free_space": free,
    }


def selfcheck() -> dict:
    """跑健康检查 + data 统计，写 last_selfcheck，返回完整结果。"""
    state = pipeline_mod.compute_state()
    checks = state["checks"]
    block_count = sum(1 for c in checks if c["status"] == "block")
    warn_count = sum(1 for c in checks if c["status"] == "warn")
    stats = _data_stats()
    result = {
        "at": _now(),
        "ok": block_count == 0,
        "block_count": block_count,
        "warn_count": warn_count,
        "checks": checks,
        "data_stats": stats,
    }
    settings_store.save(
        {
            "last_selfcheck": {
                "at": result["at"],
                "ok": result["ok"],
                "block_count": block_count,
                "warn_count": warn_count,
            }
        }
    )
    _append_log(
        {
            "kind": "selfcheck",
            "at": result["at"],
            "ok": result["ok"],
            "block_count": block_count,
            "warn_count": warn_count,
        }
    )
    return result


def auto_cleanup() -> dict:
    """自动清理：回收站超期 purge + .bak 超份数删旧 + 孤儿 run 目录。返回摘要。"""
    cfg = settings_store.load()
    retention = cfg["retention_days"]
    bak_keep = cfg["canonical_bak_keep"]

    # 1 回收站超期 -> purge（复用 store.purge，operator=system，不删 artifacts）
    purged_runs = 0
    freed = 0
    for item in store.list_trash(limit=1000):
        deleted_at = item.get("deleted_at")
        if not deleted_at:
            continue
        try:
            days = (datetime.now() - datetime.fromisoformat(deleted_at)).days
        except ValueError:
            continue
        if days >= retention:
            try:
                res = store.purge(
                    item["run_id"], "system", reason=f"自动清理：回收站超 {retention} 天"
                )
                purged_runs += 1
                freed += res.get("freed_bytes", 0)
            except (KeyError, ValueError):
                continue

    # 2 .bak 超份数 -> 删最旧（按 mtime）
    bak_dir = config.CANONICAL_BACKUPS_DIR
    deleted_baks = 0
    if bak_dir.exists():
        baks = sorted(bak_dir.glob("*.bak.xlsx"), key=lambda p: p.stat().st_mtime)
        while len(baks) > bak_keep:
            old = baks.pop(0)
            try:
                freed += old.stat().st_size
                old.unlink()
                deleted_baks += 1
            except OSError:
                break

    # 3 孤儿 run 目录（DB 无对应 run_id）
    orphans = 0
    if config.RUNS_DIR.exists():
        conn = db.connect()
        try:
            existing = {row[0] for row in conn.execute("SELECT run_id FROM runs").fetchall()}
        finally:
            conn.close()
        for d in config.RUNS_DIR.iterdir():
            if d.is_dir() and d.name not in existing:
                freed += _dir_size(d)
                shutil.rmtree(d, ignore_errors=True)
                orphans += 1

    result = {
        "at": _now(),
        "purged_runs": purged_runs,
        "deleted_baks": deleted_baks,
        "orphans": orphans,
        "freed_bytes": freed,
        "retention_days": retention,
        "bak_keep": bak_keep,
    }
    settings_store.save({"last_cleanup": result})
    _append_log({"kind": "cleanup", **result})
    return result


def _append_log(entry: dict) -> None:
    CLEANUP_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CLEANUP_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# Qwen 月度总结走公司内部 POMP 端点（免 key）。脚本收在项目 vendor/，随包分发
# （原先是 Mac 绝对路径，Windows 包上必然「脚本缺失」）。与 generate_monthly_themes.py 一致。
_POMP_SCRIPT = config.PROJECT_ROOT / "vendor" / "pomp_minimal_call.py"
_QWEN_ENDPOINT = ("pomp.ubrmbqa.com", 9997)


def _check_tcp(addr: tuple, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection(addr, timeout=timeout):
            return True
    except OSError:
        return False


def qwen_status() -> dict:
    """Qwen 月度总结状态：POMP 脚本存在 + 内部端点连通。免 key，能否用只取决于这两项。"""
    script_ok = _POMP_SCRIPT.exists()
    endpoint_ok = _check_tcp(_QWEN_ENDPOINT)
    enabled = script_ok and endpoint_ok
    if enabled:
        reason = "公司内部端点可用"
    elif not script_ok:
        reason = "POMP 脚本缺失"
    else:
        reason = "内部端点不可达（可能不在公司内网）"
    return {
        "enabled": enabled,
        "script_ok": script_ok,
        "endpoint_ok": endpoint_ok,
        "reason": reason,
    }
