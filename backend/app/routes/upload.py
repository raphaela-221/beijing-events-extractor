"""文件上传：多文件暂存到 data/uploads/<upload_id>/，返回 upload_id 供 run 接口引用。

用法：前端 Upload.Dragger 一次传 1~N 个文件 -> 拿 upload_id -> 作为 type=files
参数值 POST /api/jobs/:id/run -> build_argv 把 upload_id 解析成 --input-dir。
canonical 上传回传也走这里再单独 verify/diff/commit（P1.4）。
"""
from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, File, Request, UploadFile

from .. import config
from ..auth import require_user

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("")
async def upload(request: Request, files: list[UploadFile] = File(...)):
    require_user(request)
    if not files:
        return {"error": "未收到文件"}, 400
    upload_id = secrets.token_hex(8)
    dest_dir = config.UPLOADS_DIR / upload_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        if not f.filename:
            continue
        safe = _safe_name(f.filename)
        dest = dest_dir / safe
        sha = hashlib.sha256()
        size = 0
        with open(dest, "wb") as out_f:
            while True:
                chunk = await f.read(1024 * 1024)
                if not chunk:
                    break
                out_f.write(chunk)
                sha.update(chunk)
                size += len(chunk)
        out.append({"filename": safe, "size": size, "sha256": sha.hexdigest()})
    return {"upload_id": upload_id, "dir": str(dest_dir), "files": out}


def _safe_name(name: str) -> str:
    """取 basename 防路径穿越。"""
    from pathlib import Path

    return Path(name).name
