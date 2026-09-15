"""Run 路由：列表 / 详情 / 日志分页 / 下载 / 取消 / SSE 流 + P2-A 管理（置顶/删除/回收站/批量/对比/导出/审计）。"""
from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from openpyxl import Workbook
from pydantic import BaseModel

from .. import config
from ..auth import require_admin, require_user
from ..jobs import runner
from ..runs import store

router = APIRouter(prefix="/api/runs", tags=["runs"])


# ---- 静态路径（必须在 /{run_id} 之前，否则被当 run_id）----


@router.get("")
def list_runs(
    request: Request,
    op_id: Optional[list[str]] = Query(default=None),
    status: Optional[list[str]] = Query(default=None),
    operator: Optional[str] = None,
    started_from: Optional[str] = None,
    started_to: Optional[str] = None,
    pinned: Optional[bool] = None,
    sort: str = "started_at:desc",
    page: int = 1,
    page_size: int = 20,
):
    require_user(request)
    return store.list_runs(
        op_id=op_id, status=status, operator=operator,
        started_from=started_from, started_to=started_to, pinned=pinned,
        sort=sort, page=page, page_size=page_size,
    )


@router.get("/trash")
def list_trash(request: Request):
    require_user(request)
    return {"items": store.list_trash()}


@router.get("/deletions")
def list_deletions(request: Request):
    """删除审计（管理员）。"""
    require_admin(request)
    return {"items": store.list_deletions()}


class PurgeFilters(BaseModel):
    op_id: Optional[list[str]] = None
    status: Optional[list[str]] = None
    operator: Optional[str] = None
    started_from: Optional[str] = None
    started_to: Optional[str] = None
    keep_pinned: bool = True


@router.post("/purge-preview")
def purge_preview(request: Request, filters: PurgeFilters):
    require_user(request)
    return store.purge_preview(filters.model_dump())


class BulkDeleteIn(BaseModel):
    filters: PurgeFilters
    mode: str = "trash"  # trash | purge
    delete_artifacts: bool = False


@router.post("/bulk-delete")
def bulk_delete(request: Request, body: BulkDeleteIn):
    user = require_user(request)
    if body.mode not in ("trash", "purge"):
        raise HTTPException(status_code=400, detail="mode 必须是 trash 或 purge")
    if body.mode == "purge":
        require_admin(request)  # 彻底删除限管理员
    return store.bulk_delete(
        body.filters.model_dump(), body.mode, body.delete_artifacts, user["username"]
    )


@router.get("/export.xlsx")
def export_runs(
    request: Request,
    op_id: Optional[list[str]] = Query(default=None),
    status: Optional[list[str]] = Query(default=None),
    operator: Optional[str] = None,
    started_from: Optional[str] = None,
    started_to: Optional[str] = None,
    pinned: Optional[bool] = None,
    sort: str = "started_at:desc",
):
    """当前筛选结果导出 xlsx（非 canonical，openpyxl 新建 save 安全）。"""
    require_user(request)
    page = store.list_runs(
        op_id=op_id, status=status, operator=operator,
        started_from=started_from, started_to=started_to, pinned=pinned,
        sort=sort, page=1, page_size=100000,
    )
    items = page["items"]

    def _key_summary(r: dict) -> str:
        try:
            s = json.loads(r.get("summary_json") or "{}")
        except json.JSONDecodeError:
            return ""
        concert = s.get("concert") or {}
        pipeline = s.get("pipeline") or {}
        parts = []
        if concert.get("final") is not None:
            parts.append(f"演唱会 {concert['final']} 条")
        ex = pipeline.get("extract") or {}
        if ex.get("事件数") is not None:
            parts.append(f"事件 {ex['事件数']}")
        th = pipeline.get("themes") or {}
        if th.get("生成") is not None:
            parts.append(f"主题生成 {th['生成']}")
        return " · ".join(parts)

    wb = Workbook()
    ws = wb.active
    ws.title = "运行记录"
    ws.append(["时间", "操作", "分组", "状态", "操作人", "用时(秒)", "退出码", "错误摘要", "关键摘要", "运行编号"])
    for r in items:
        ws.append([
            r.get("started_at", ""),
            r.get("op_label", ""),
            r.get("op_group", ""),
            r.get("status", ""),
            r.get("operator", ""),
            round((r.get("duration_ms") or 0) / 1000, 1),
            r.get("exit_code"),
            r.get("error_summary") or "",
            _key_summary(r),
            r.get("run_id", ""),
        ])
    for col, w in zip("ABCDEFGHIJ", [18, 22, 12, 10, 10, 10, 8, 30, 24, 36]):
        ws.column_dimensions[col].width = w
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="runs.xlsx"'},
    )


# ---- 单条 /{run_id} ----


@router.get("/{run_id}")
def get_run(run_id: str, request: Request):
    require_user(request)
    r = store.get_run(run_id)
    if not r:
        raise HTTPException(status_code=404, detail="运行不存在")
    return r


@router.get("/{run_id}/output")
def download_output(run_id: str, request: Request):
    """下载 Step1 类 run 的产出 Excel。

    Step1 脚本（01_event_extractor/main.py）实际不写 canonical Events List.xlsx，
    而是写带运行日期的 Travel_Facilitators_and_Hindrances_Events_{YYYY.MM.DD}.xlsx
    到 01_event_list_output/。这里按 run 的开始日期定位该文件供前端下载，
    代替让用户上服务器翻文件夹。
    """
    require_user(request)
    r = store.get_run(run_id)
    if not r:
        raise HTTPException(status_code=404, detail="运行不存在")
    if r.get("op_id") not in ("step1_full", "step1_input_only", "step1_concert_only"):
        raise HTTPException(status_code=404, detail="该操作类型没有独立产出文件")
    # started_at 形如 2026-08-07T22:12:29；文件名日期 = 运行当天（脚本用本地 now()）
    try:
        day = datetime.fromisoformat(r["started_at"]).strftime("%Y.%m.%d")
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="运行缺少开始时间，无法定位产出文件")
    fname = f"Travel_Facilitators_and_Hindrances_Events_{day}.xlsx"
    p = (config.PROJECT_ROOT / "01_event_list_output" / fname).resolve()
    # 防路径穿越：必须落在 01_event_list_output/ 内（fname 是内部拼接的，此为双保险）
    if not str(p).startswith(str((config.PROJECT_ROOT / "01_event_list_output").resolve())):
        raise HTTPException(status_code=400, detail="非法路径")
    if not p.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"产出文件 {fname} 不存在（当天多次运行会互相覆盖合并，若运行失败则可能未生成）",
        )
    return FileResponse(
        str(p),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=fname,
    )


@router.get("/{run_id}/log")
def get_log(run_id: str, request: Request, from_seq: int = 0, limit: int = 2000):
    require_user(request)
    if not store.get_run(run_id):
        raise HTTPException(status_code=404, detail="运行不存在")
    return store.list_logs(run_id, from_seq, limit)


@router.get("/{run_id}/log/download")
def download_log(run_id: str, request: Request):
    require_user(request)
    if not store.get_run(run_id):
        raise HTTPException(status_code=404, detail="运行不存在")
    p = config.RUNS_DIR / run_id / "stdout.log"
    if not p.exists():
        raise HTTPException(status_code=404, detail="日志文件不存在")
    return PlainTextResponse(
        p.read_text(encoding="utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.log"'},
    )


@router.get("/{run_id}/compare")
def compare_run(run_id: str, request: Request):
    require_user(request)
    if not store.get_run(run_id):
        raise HTTPException(status_code=404, detail="运行不存在")
    return store.compare_with_last(run_id)


@router.post("/{run_id}/cancel")
async def cancel(run_id: str, request: Request):
    require_user(request)
    if not store.get_run(run_id):
        raise HTTPException(status_code=404, detail="运行不存在")
    ok = await runner.mgr.cancel(run_id)
    if not ok:
        raise HTTPException(status_code=409, detail="任务不在运行中")
    return {"ok": True}


@router.get("/{run_id}/stream")
async def stream(run_id: str, request: Request, from_seq: int = 0):
    require_user(request)
    if not store.get_run(run_id):
        raise HTTPException(status_code=404, detail="运行不存在")
    return StreamingResponse(
        runner.mgr.sse_stream(run_id, from_seq, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 防 nginx 缓冲
        },
    )


# ---- P2-A 管理：置顶 / 删除 / 恢复 ----


class PinIn(BaseModel):
    pinned: bool


@router.post("/{run_id}/pin")
def pin_run(run_id: str, request: Request, body: PinIn):
    require_user(request)
    if not store.get_run(run_id):
        raise HTTPException(status_code=404, detail="运行不存在")
    store.set_pinned(run_id, body.pinned)
    return {"run_id": run_id, "pinned": body.pinned}


@router.delete("/{run_id}")
def delete_run(
    run_id: str,
    request: Request,
    mode: str = "trash",
    delete_artifacts: bool = False,
):
    """软删（trash，进回收站 30 天可恢复）或彻底删（purge，限管理员）。运行中 409。"""
    user = require_user(request)
    if mode not in ("trash", "purge"):
        raise HTTPException(status_code=400, detail="mode 必须是 trash 或 purge")
    if mode == "purge":
        require_admin(request)
    if not store.get_run(run_id):
        raise HTTPException(status_code=404, detail="运行不存在")
    if runner.mgr.is_running(run_id):
        raise HTTPException(status_code=409, detail="任务仍在运行，请先取消")
    try:
        if mode == "purge":
            return store.purge(
                run_id, user["username"], delete_artifacts=delete_artifacts, reason="manual"
            )
        return store.soft_delete(run_id, user["username"])
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{run_id}/restore")
def restore_run(run_id: str, request: Request):
    require_user(request)
    try:
        return store.restore(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="运行不存在")
