"""编辑锁路由。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..auth import require_user
from ..lock import lock

router = APIRouter(prefix="/api/lock", tags=["lock"])


@router.get("")
def status(request: Request):
    require_user(request)
    h = lock.status()
    if not h:
        return {"held": False}
    me = require_user(request)
    return {
        "held": True,
        "holder": h["user"],
        "since": h["since"],
        "is_me": h["user"] == me["username"],
    }


@router.post("/acquire")
def acquire(request: Request):
    user = require_user(request)
    if not lock.acquire(user["username"]):
        h = lock.status()
        raise HTTPException(
            status_code=409,
            detail=f"编辑锁被占用：{h['user']}（{h['since']} 起）",
        )
    h = lock.status()
    return {"held": True, "holder": h["user"], "since": h["since"], "is_me": True}


@router.post("/release")
def release(request: Request):
    user = require_user(request)
    ok = lock.release(user["username"])
    if not ok:
        # 非持有者：仅管理员可强制释放
        h = lock.status()
        if user["role"] == "admin" and h:
            lock.force_release()
            return {"held": False, "released_from": h["user"]}
        if h:
            raise HTTPException(
                status_code=409,
                detail=f"编辑锁由 {h['user']} 持有，你无权释放",
            )
    return {"held": False}
