"""runs 表读写 + run 目录 + .bak。"""
from __future__ import annotations

import json
import os
import secrets
import shutil
from datetime import datetime
from pathlib import Path

from .. import config, db

TRASH_RETENTION_DAYS = 30


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def gen_run_id(op_id: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    suffix = secrets.token_hex(2)  # 4 hex
    return f"{stamp}-{op_id}-{suffix}"


def run_dir(run_id: str) -> Path:
    return config.RUNS_DIR / run_id


def create_run(
    op_id: str,
    op_label: str,
    op_group: str,
    params: dict,
    operator: str,
    preset: str | None = None,
) -> str:
    run_id = gen_run_id(op_id)
    rd = run_dir(run_id)
    rd.mkdir(parents=True, exist_ok=True)
    log_path = rd / "stdout.jsonl"
    started = _now()
    meta = {
        "run_id": run_id,
        "op_id": op_id,
        "op_label": op_label,
        "op_group": op_group,
        "operator": operator,
        "started_at": started,
        "params": params,
    }
    (rd / "params.json").write_text(
        json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (rd / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    conn = db.connect()
    try:
        conn.execute(
            """INSERT INTO runs
               (run_id, op_id, op_label, op_group, preset, params_json,
                status, started_at, operator, log_path)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                op_id,
                op_label,
                op_group,
                preset,
                json.dumps(params, ensure_ascii=False),
                "queued",
                started,
                operator,
                str(log_path),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def get_run(run_id: str) -> dict | None:
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_run(run_id: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [run_id]
    conn = db.connect()
    try:
        conn.execute(f"UPDATE runs SET {cols} WHERE run_id=?", vals)
        conn.commit()
    finally:
        conn.close()


def backup_canonical(run_id: str) -> str | None:
    """运行前备份 canonical 到 data/canonical/backups/。"""
    if not config.CANONICAL_PATH.exists():
        return None
    config.CANONICAL_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    bak = config.CANONICAL_BACKUPS_DIR / f"Events List.{run_id}.bak.xlsx"
    shutil.copy2(config.CANONICAL_PATH, bak)
    return str(bak)


def list_logs(run_id: str, from_seq: int = 0, limit: int = 2000) -> dict:
    """返回 seq > from_seq 的日志行（最多 limit）+ 总行数 + 是否还有更多。"""
    rd = run_dir(run_id)
    jsonl = rd / "stdout.jsonl"
    lines: list[dict] = []
    if jsonl.exists():
        with open(jsonl, encoding="utf-8") as f:
            for raw in f:
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if rec.get("seq", 0) <= from_seq:
                    continue
                lines.append(rec)
                if len(lines) >= limit:
                    break
    run = get_run(run_id) or {}
    total = run.get("log_lines") or 0
    last_seq = lines[-1]["seq"] if lines else from_seq
    return {"lines": lines, "total": total, "last_seq": last_seq, "has_more": last_seq < total}


def list_runs(
    op_id: list[str] | None = None,
    status: list[str] | None = None,
    operator: str | None = None,
    started_from: str | None = None,
    started_to: str | None = None,
    pinned: bool | None = None,
    sort: str = "started_at:desc",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """运行记录列表查询（指南附录 B）。默认排除已软删。"""
    where = ["deleted_at IS NULL"]
    vals: list = []
    if op_id:
        where.append(f"op_id IN ({','.join('?' * len(op_id))})")
        vals += op_id
    if status:
        where.append(f"status IN ({','.join('?' * len(status))})")
        vals += status
    if operator:
        where.append("operator=?")
        vals.append(operator)
    if started_from:
        where.append("started_at>=?")
        vals.append(started_from)
    if started_to:
        where.append("started_at<=?")
        vals.append(started_to)
    if pinned is not None:
        where.append("pinned=?")
        vals.append(1 if pinned else 0)
    clause = " WHERE " + " AND ".join(where)
    sort_col, _, sort_dir = sort.partition(":")
    allowed = {"started_at", "ended_at", "duration_ms", "op_label", "status"}
    if sort_col not in allowed:
        sort_col = "started_at"
    order = f" ORDER BY {sort_col} {'ASC' if sort_dir.lower()=='asc' else 'DESC'}"
    conn = db.connect()
    try:
        total = conn.execute(f"SELECT count(*) FROM runs{clause}", vals).fetchone()[0]
        offset = max(0, (page - 1) * page_size)
        rows = conn.execute(
            f"SELECT * FROM runs{clause}{order} LIMIT ? OFFSET ?",
            vals + [page_size, offset],
        ).fetchall()
        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    finally:
        conn.close()


def runs_since(started_after: str, op_ids: list[str] | None = None) -> list[dict]:
    """查某时间点之后、修改过 canonical 的运行（核对往返 intervening_runs，§5.5）。
    op_ids 默认取所有 write_canonical/destructive 的抽取类操作。"""
    where = ["deleted_at IS NULL", "started_at>?", "status IN ('success','failed','cancelled')"]
    vals: list = [started_after]
    if op_ids:
        where.append(f"op_id IN ({','.join('?' * len(op_ids))})")
        vals += op_ids
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM runs WHERE " + " AND ".join(where) + " ORDER BY started_at ASC",
            vals,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def parse_duration_ms(started_at: str, ended_at: str) -> int:
    try:
        s = datetime.fromisoformat(started_at)
        e = datetime.fromisoformat(ended_at)
        return int((e - s).total_seconds() * 1000)
    except Exception:
        return 0


def list_publishes(limit: int = 20) -> list[dict]:
    """发布历史：最近 limit 条（P1.6 发布页）。"""
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT publish_id, created_at, operator, zip_path, note "
            "FROM publishes ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_publish(operator: str, zip_path: str | None, note: str | None) -> dict:
    """标记一次发布完成，写 publishes 表（不跑脚本）。"""
    publish_id = f"pub-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    created = _now()
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO publishes (publish_id, created_at, operator, zip_path, note) "
            "VALUES (?,?,?,?,?)",
            (publish_id, created, operator, zip_path, note),
        )
        conn.commit()
        return {
            "publish_id": publish_id,
            "created_at": created,
            "operator": operator,
            "zip_path": zip_path,
            "note": note,
        }
    finally:
        conn.close()


# ---- P2-A 运行记录管理：置顶 / 删除 / 回收站 / 批量 / 对比 / 审计 ----


def _dir_size(p: Path) -> int:
    """目录总字节数（递归）。不存在返回 0。"""
    if not p.exists():
        return 0
    total = 0
    for root, _, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _days_since(iso: str | None) -> int:
    if not iso:
        return 0
    try:
        return (datetime.now() - datetime.fromisoformat(iso)).days
    except Exception:
        return 0


def _write_deletion_audit(
    run_id: str,
    op_label: str,
    run_started_at: str | None,
    deleted_by: str,
    mode: str,
    reason: str | None,
    artifacts_deleted: int,
    freed_bytes: int,
) -> None:
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO run_deletions "
            "(run_id, op_label, run_started_at, deleted_at, deleted_by, mode, reason, artifacts_deleted, freed_bytes) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, op_label, run_started_at, _now(), deleted_by, mode, reason, artifacts_deleted, freed_bytes),
        )
        conn.commit()
    finally:
        conn.close()


def set_pinned(run_id: str, pinned: bool) -> None:
    conn = db.connect()
    try:
        conn.execute("UPDATE runs SET pinned=? WHERE run_id=?", (1 if pinned else 0, run_id))
        conn.commit()
    finally:
        conn.close()


def soft_delete(run_id: str, operator: str) -> dict:
    """软删：写 deleted_at，进回收站。运行中拒。.bak 不动。"""
    r = get_run(run_id)
    if not r:
        raise KeyError("运行不存在")
    if r["status"] in ("queued", "running"):
        raise ValueError("运行中不可删除")
    conn = db.connect()
    try:
        conn.execute("UPDATE runs SET deleted_at=? WHERE run_id=?", (_now(), run_id))
        conn.commit()
    finally:
        conn.close()
    _write_deletion_audit(run_id, r["op_label"], r["started_at"], operator, "trash", None, 0, 0)
    return {"run_id": run_id, "mode": "trash"}


def purge(
    run_id: str,
    operator: str,
    delete_artifacts: bool = False,
    reason: str | None = None,
) -> dict:
    """彻底删：删 DB 行 + 删 data/runs/<id>/ 目录。.bak 永不删（指南 §4.2 规则 3）。"""
    r = get_run(run_id)
    if not r:
        raise KeyError("运行不存在")
    if r["status"] in ("queued", "running"):
        raise ValueError("运行中不可删除")
    rd = run_dir(run_id)
    freed = _dir_size(rd)
    artifacts_deleted = 0
    if delete_artifacts:
        try:
            arts = json.loads(r.get("artifacts_json") or "[]")
        except json.JSONDecodeError:
            arts = []
        for a in arts:
            if not isinstance(a, dict) or not a.get("exists") or not a.get("path"):
                continue
            ap = config.PROJECT_ROOT / a["path"]
            # 安全：绝不碰 canonical backups（.bak 唯一回滚绳）
            parts = {p.lower() for p in ap.parts}
            if "backups" in parts or ap == config.CANONICAL_PATH:
                continue
            try:
                freed += ap.stat().st_size
                ap.unlink()
                artifacts_deleted += 1
            except OSError:
                pass
    if rd.exists():
        shutil.rmtree(rd, ignore_errors=True)
    conn = db.connect()
    try:
        conn.execute("DELETE FROM runs WHERE run_id=?", (run_id,))
        conn.commit()
    finally:
        conn.close()
    _write_deletion_audit(
        run_id, r["op_label"], r["started_at"], operator, "purge", reason, artifacts_deleted, freed
    )
    return {"run_id": run_id, "mode": "purge", "freed_bytes": freed, "artifacts_deleted": artifacts_deleted}


def restore(run_id: str) -> dict:
    conn = db.connect()
    try:
        cur = conn.execute("UPDATE runs SET deleted_at=NULL WHERE run_id=?", (run_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise KeyError("运行不存在")
    finally:
        conn.close()
    return {"run_id": run_id, "restored": True}


def list_trash(limit: int = 200) -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM runs WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    items = []
    for r in rows:
        d = dict(r)
        d["days_left"] = max(0, TRASH_RETENTION_DAYS - _days_since(d["deleted_at"]))
        items.append(d)
    return items


def _purge_clause(filters: dict) -> tuple[str, list]:
    """purge 可删候选的 WHERE：deleted_at IS NULL + 非运行中。pinned/最后成功在外层排除。"""
    where = ["deleted_at IS NULL", "status NOT IN ('queued','running')"]
    vals: list = []
    op_ids = filters.get("op_id") or []
    if op_ids:
        where.append(f"op_id IN ({','.join('?' * len(op_ids))})")
        vals += op_ids
    statuses = filters.get("status") or []
    if statuses:
        where.append(f"status IN ({','.join('?' * len(statuses))})")
        vals += statuses
    if filters.get("operator"):
        where.append("operator=?")
        vals.append(filters["operator"])
    if filters.get("started_to"):
        where.append("started_at<=?")
        vals.append(filters["started_to"])
    if filters.get("started_from"):
        where.append("started_at>=?")
        vals.append(filters["started_from"])
    return " AND ".join(where), vals


def _resolve_purge_targets(filters: dict) -> tuple[list[dict], list[dict], int]:
    """返回 (to_delete, protected, freed_bytes)。
    排除：pinned（keep_pinned=True 时）、每个 op_id 最近 1 次 success（指南 §4.2 规则 4）。"""
    clause, vals = _purge_clause(filters)
    conn = db.connect()
    try:
        rows = conn.execute(
            f"SELECT * FROM runs WHERE {clause} ORDER BY started_at ASC", vals
        ).fetchall()
    finally:
        conn.close()
    rows = [dict(r) for r in rows]

    keep_pinned = filters.get("keep_pinned", True)
    protected: list[dict] = []
    candidates: list[dict] = []
    for r in rows:
        if keep_pinned and r["pinned"]:
            protected.append({"run_id": r["run_id"], "op_label": r["op_label"], "reason": "已置顶"})
            continue
        candidates.append(r)

    # 每 op_id 最近 1 次 success
    last_success: dict[str, str] = {}
    for r in sorted(rows, key=lambda x: x["started_at"], reverse=True):
        if r["status"] == "success" and r["op_id"] not in last_success:
            last_success[r["op_id"]] = r["run_id"]
    final: list[dict] = []
    for r in candidates:
        if last_success.get(r["op_id"]) == r["run_id"]:
            protected.append(
                {"run_id": r["run_id"], "op_label": r["op_label"], "reason": "该操作最后一次成功记录"}
            )
            continue
        final.append(r)
    freed = sum(_dir_size(run_dir(r["run_id"])) for r in final)
    return final, protected, freed


def purge_preview(filters: dict) -> dict:
    final, protected, freed = _resolve_purge_targets(filters)
    pinned_count = sum(1 for p in protected if p["reason"] == "已置顶")
    last_success_count = sum(1 for p in protected if "最后" in p["reason"])
    sample = [
        {
            "run_id": r["run_id"],
            "op_label": r["op_label"],
            "started_at": r["started_at"],
            "status": r["status"],
        }
        for r in final[:5]
    ]
    return {
        "count": len(final),
        "freed_bytes": freed,
        "protected_count": len(protected),
        "pinned_count": pinned_count,
        "last_success_count": last_success_count,
        "protected_reasons": protected,
        "sample": sample,
    }


def bulk_delete(
    filters: dict, mode: str, delete_artifacts: bool, operator: str
) -> dict:
    final, protected, _ = _resolve_purge_targets(filters)
    deleted: list[dict] = []
    freed = 0
    for r in final:
        if mode == "purge":
            res = purge(
                r["run_id"], operator, delete_artifacts=delete_artifacts, reason="bulk-delete"
            )
            freed += res["freed_bytes"]
        else:
            soft_delete(r["run_id"], operator)
        deleted.append({"run_id": r["run_id"], "op_label": r["op_label"]})
    return {
        "deleted_count": len(deleted),
        "freed_bytes": freed,
        "protected_count": len(protected),
        "deleted": deleted,
    }


def _summary_nums(run: dict) -> dict:
    """从 summary_json / llm_json 宽松提取对比数字。best-effort，缺则 0。"""
    try:
        s = json.loads(run.get("summary_json") or "{}")
    except json.JSONDecodeError:
        s = {}
    concert = (s.get("concert") or {}) if isinstance(s, dict) else {}
    pipeline = (s.get("pipeline") or {}) if isinstance(s, dict) else {}
    extract = pipeline.get("extract") or {}
    events = concert.get("final") or extract.get("事件数") or 0
    try:
        llm = json.loads(run.get("llm_json") or "{}")
    except json.JSONDecodeError:
        llm = {}
    total = llm.get("total") or {}
    tokens = total.get("tokens") or 0
    return {"events": events, "tokens": tokens}


def compare_with_last(run_id: str) -> dict:
    """与同 op_id 上一次成功运行差值（用时 / 事件数 / token）。无则 has_previous=False。"""
    r = get_run(run_id)
    if not r:
        raise KeyError("运行不存在")
    conn = db.connect()
    try:
        prev = conn.execute(
            "SELECT * FROM runs WHERE op_id=? AND status='success' AND deleted_at IS NULL "
            "AND started_at < ? ORDER BY started_at DESC LIMIT 1",
            (r["op_id"], r["started_at"]),
        ).fetchone()
    finally:
        conn.close()
    if not prev:
        return {"has_previous": False}
    prev = dict(prev)
    cur_s = _summary_nums(r)
    prev_s = _summary_nums(prev)
    return {
        "has_previous": True,
        "previous_run_id": prev["run_id"],
        "previous_started_at": prev["started_at"],
        "duration_ms_delta": (r.get("duration_ms") or 0) - (prev.get("duration_ms") or 0),
        "events_delta": (cur_s["events"] or 0) - (prev_s["events"] or 0),
        "tokens_delta": (cur_s["tokens"] or 0) - (prev_s["tokens"] or 0),
        "current": cur_s,
        "previous": prev_s,
    }


def list_deletions(limit: int = 200) -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT * FROM run_deletions ORDER BY deleted_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def last_run_per_op() -> dict:
    """每 op_id 最近一条 run（工具箱卡片「上次运行」用）。"""
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT op_id, run_id, started_at, status FROM runs "
            "WHERE deleted_at IS NULL ORDER BY started_at DESC"
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        if d["op_id"] not in out:
            out[d["op_id"]] = {
                "run_id": d["run_id"],
                "started_at": d["started_at"],
                "status": d["status"],
            }
    return out
