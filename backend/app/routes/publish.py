"""发布路由（P1.6）：预览托管状态 / 生成 zip / 下载 / 标记已发布 / 历史。

- /preview/* 由 main.py 的 StaticFiles 托管 02_web_output/，本路由只给 state/zip/download/mark-done/history。
- 生成 zip 前必须 verify_canonical 通过（指南：canonical 损坏阻断发布）。
- zip 同步生成（几 MB，不走 job 系统）；mark-done 仅写 publishes 表，不跑脚本。
"""
from __future__ import annotations

import re
import subprocess
import sys
import shutil
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import config, settings_store
from ..auth import require_admin, require_user
from ..runs import store

router = APIRouter(prefix="/api/publish", tags=["publish"])


def _verify_canonical() -> int:
    """跑 verify_canonical.py --quiet。0=完好 1=损坏 2=不存在。与 pipeline.py 同逻辑，避免跨 route 耦合。"""
    script = config.CALENDAR_DIR / "verify_canonical.py"
    if not script.exists():
        return 2
    try:
        r = subprocess.run(
            [sys.executable, str(script), "--quiet"],
            capture_output=True,
            timeout=30,
        )
        return r.returncode
    except Exception:
        return 1


def _latest_zip() -> Optional[dict]:
    """data/publishes/ 下最新 zip（按 mtime），用于刷新页面后仍知道有 zip 可下载（持久化）。"""
    if not config.PUBLISHES_DIR.exists():
        return None
    zips = sorted(
        config.PUBLISHES_DIR.glob("*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not zips:
        return None
    p = zips[0]
    st = p.stat()
    return {
        "name": p.name,
        "size_bytes": st.st_size,
        "created_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }


@router.get("/state")
def get_state(request: Request):
    require_user(request)
    # 未配 EXTERNAL_SHARE_URL 时回退为本机直链：优先对外别名路径 /<路径名>/，
    # 没开别名才用 /preview/index.html。静态托管不走登录，局域网内可直接分享。
    external = config.EXTERNAL_SHARE_URL
    external_source = "env"
    slug = settings_store.effective_share_path()
    if not external:
        base = str(request.base_url).rstrip("/")
        if slug and slug != "-":
            external = f"{base}/{slug}/"
        else:
            external = f"{base}/preview/index.html"
        external_source = "self"
    return {
        "preview_path": "/preview/index.html",
        "external_url": external,
        "external_url_source": external_source,
        "share_path": slug,
        "platform_upload_url": config.PLATFORM_UPLOAD_URL,
        "canonical_ok": _verify_canonical() == 0,
        "latest_zip": _latest_zip(),
    }


# 别名路径规则：字母/数字/短横线，1-64 位，以字母或数字开头（防 /.. 穿越等）
_SHARE_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SHARE_PATH_RESERVED = {"api", "preview", "assets"}


class SharePathBody(BaseModel):
    path: str


@router.post("/share-path")
def set_share_path(body: SharePathBody, request: Request):
    """admin 改对外别名路径，保存进 settings.json 并热重挂 mount（不重启）。
    清空 = 恢复默认（beijing-events-calendar）；填 - 关闭别名（回退 /preview 直链）。"""
    require_admin(request)
    p = body.path.strip().strip("/")
    if p and p != "-":
        if not _SHARE_PATH_RE.match(p):
            raise HTTPException(400, "路径名只能用字母/数字/短横线，1-64 位，且以字母或数字开头")
        if p.lower() in _SHARE_PATH_RESERVED:
            raise HTTPException(400, f"{p} 是系统保留路径，换一个")
    settings_store.save({"share_path": p or None})
    from ..main import apply_external_share_mount  # 延迟导入避免循环
    apply_external_share_mount()
    return {"share_path": settings_store.effective_share_path()}


@router.post("/zip")
def make_zip(request: Request):
    user = require_user(request)
    if _verify_canonical() != 0:
        raise HTTPException(status_code=409, detail="canonical 结构损坏，发布已阻断，请先修复后再生成 zip")
    if not config.WEB_OUTPUT_DIR.exists() or not any(config.WEB_OUTPUT_DIR.iterdir()):
        raise HTTPException(status_code=409, detail="02_web_output/ 为空，请先在 Step 2 跑「打包分享文件」")
    config.PUBLISHES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_name = f"beijing-events-{stamp}.zip"
    zip_path = config.PUBLISHES_DIR / zip_name
    # make_archive 自动加 .zip 后缀，传去掉后缀的 base
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", str(config.WEB_OUTPUT_DIR))
    st = zip_path.stat()
    return {
        "zip_name": zip_name,
        "size_bytes": st.st_size,
        "created_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }


@router.get("/download/{zip_name}")
def download_zip(zip_name: str, request: Request):
    require_user(request)
    # 防路径穿越：文件名不含分隔符或 ..，且必须在 PUBLISHES_DIR 内
    if "/" in zip_name or "\\" in zip_name or ".." in zip_name:
        raise HTTPException(status_code=400, detail="非法文件名")
    p = (config.PUBLISHES_DIR / zip_name).resolve()
    if not str(p).startswith(str(config.PUBLISHES_DIR.resolve())):
        raise HTTPException(status_code=400, detail="非法文件名")
    if not p.is_file():
        raise HTTPException(status_code=404, detail="zip 不存在")
    return FileResponse(str(p), media_type="application/zip", filename=zip_name)


class MarkDoneBody(BaseModel):
    zip_name: Optional[str] = None
    note: Optional[str] = None


@router.post("/mark-done")
def mark_done(body: MarkDoneBody, request: Request):
    user = require_user(request)
    operator = user.get("username", "unknown")
    zip_path = str(config.PUBLISHES_DIR / body.zip_name) if body.zip_name else None
    return store.create_publish(operator, zip_path, body.note)


@router.get("/history")
def history(request: Request):
    require_user(request)
    return store.list_publishes(limit=20)
