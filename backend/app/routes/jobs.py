"""Job 路由：列表 / schema / 发起运行。"""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_user
from ..jobs import registry, runner
from ..lock import lock
from ..runs import store

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(request: Request):
    require_user(request)
    return [j.to_schema() for j in registry.list_jobs()]


@router.get("/last-runs")
def last_runs(request: Request):
    """每 op_id 最近一条 run（工具箱卡片「上次运行」）。"""
    require_user(request)
    return store.last_run_per_op()


@router.get("/{job_id}")
def get_job(job_id: str, request: Request):
    require_user(request)
    j = registry.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="操作不存在")
    return j.to_schema()


@router.post("/{job_id}/run")
async def run_job(job_id: str, request: Request):
    user = require_user(request)
    j = registry.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="操作不存在")
    if j.admin_only and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    body = await request.json()
    params = body.get("params", {}) or {}
    preset = body.get("preset")

    # preflight
    problems = registry.run_preflight(j)
    if problems:
        raise HTTPException(
            status_code=409,
            detail="LLM API key 未配置或已失效，请在 .env 配置 DeepSeek/Ark key",
        )

    # 全局单运行任务
    if runner.mgr.any_running():
        raise HTTPException(status_code=409, detail="已有任务在运行，请等其结束或取消")

    # 编辑锁
    if not lock.acquire(user["username"]):
        h = lock.status()
        raise HTTPException(
            status_code=409,
            detail=f"编辑锁被占用：{h['user']}（{h['since']} 起）",
        )

    run_id = store.create_run(j.id, j.label, j.group, params, user["username"], preset)

    # 写 canonical 前备份
    if j.danger in ("write_canonical", "destructive"):
        bak = store.backup_canonical(run_id)
        if bak:
            store.update_run(run_id, canonical_backup_path=bak)

    argv = registry.build_argv(j, params)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    try:
        await runner.mgr.start(run_id, argv, env, j.stages, danger=j.danger)
    except Exception as e:
        lock.release(user["username"])
        store.update_run(
            run_id,
            status="failed",
            error_summary=f"启动失败: {e}",
            ended_at=datetime.now().isoformat(timespec="seconds"),
        )
        raise HTTPException(status_code=500, detail=str(e))

    return {"run_id": run_id}
