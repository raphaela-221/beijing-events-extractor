"""设置页：运行配置 + 自检 + 自动清理。

- GET  /api/settings         任意角色：看设置/key 状态/data 统计/上次自检/上次清理
- POST /api/settings         admin：改 retention_days / canonical_bak_keep
- POST /api/settings/selfcheck  admin：立即自检
- POST /api/settings/cleanup   admin：立即清理
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import config, maintenance, settings_store
from ..auth import require_admin, require_user

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    retention_days: Optional[int] = None
    canonical_bak_keep: Optional[int] = None


@router.get("")
def get_settings(request: Request):
    require_user(request)
    cfg = settings_store.load()
    ds = bool(os.getenv("OPENAI_API_KEY", "").strip())
    ark = bool(os.getenv("ARK_API_KEY", "").strip())
    return {
        "retention_days": cfg["retention_days"],
        "canonical_bak_keep": cfg["canonical_bak_keep"],
        "last_selfcheck": cfg.get("last_selfcheck"),
        "last_cleanup": cfg.get("last_cleanup"),
        "keys": {"deepseek": ds, "ark": ark},
        "data_stats": maintenance._data_stats(),
    }


@router.post("")
def update_settings(request: Request, body: SettingsUpdate):
    require_admin(request)
    updates: dict = {}
    if body.retention_days is not None:
        if not 1 <= body.retention_days <= 365:
            raise HTTPException(400, "retention_days 须在 1-365")
        updates["retention_days"] = body.retention_days
    if body.canonical_bak_keep is not None:
        if not 1 <= body.canonical_bak_keep <= 100:
            raise HTTPException(400, "canonical_bak_keep 须在 1-100")
        updates["canonical_bak_keep"] = body.canonical_bak_keep
    if not updates:
        raise HTTPException(400, "未提供可更新字段")
    cfg = settings_store.save(updates)
    return {
        "retention_days": cfg["retention_days"],
        "canonical_bak_keep": cfg["canonical_bak_keep"],
    }


@router.post("/selfcheck")
def run_selfcheck(request: Request):
    require_admin(request)
    return maintenance.selfcheck()


@router.post("/cleanup")
def run_cleanup(request: Request):
    require_admin(request)
    return maintenance.auto_cleanup()


class KeyProviderUpdate(BaseModel):
    key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


class KeysUpdate(BaseModel):
    deepseek: Optional[KeyProviderUpdate] = None
    ark: Optional[KeyProviderUpdate] = None
    mlamp: Optional[KeyProviderUpdate] = None


@router.get("/keys")
def get_keys(request: Request):
    """key 遮罩回显（首2+末4），base_url/model 明文。qwen 状态（免 key）。

    configured/masked 从 os.getenv 读（= .env 或 llm_keys.json 注入后的实际生效值），
    这样 .env 里配了 key、llm_keys.json 还没存过时也能正确显示「已配置」，
    而不是误报「未配置」。base_url/model 缺省时用 KEY_DEFAULTS 兜底。
    """
    require_user(request)

    def _read(prefix: str) -> dict:
        key = os.getenv(f"{prefix}_API_KEY", "") or ""
        return {
            "configured": bool(key),
            "masked": settings_store.mask_key(key),
            "base_url": os.getenv(f"{prefix}_BASE_URL")
            or settings_store.KEY_DEFAULTS.get(f"{prefix}_BASE_URL", ""),
            "model": os.getenv(f"{prefix}_MODEL")
            or settings_store.KEY_DEFAULTS.get(f"{prefix}_MODEL", ""),
        }

    return {
        "deepseek": _read("OPENAI"),
        "ark": _read("ARK"),
        "mlamp": _read("MLAMP"),
        "qwen": maintenance.qwen_status(),
    }


@router.post("/keys")
def update_keys(request: Request, body: KeysUpdate):
    """admin 改 key/base_url/model。key 字段不发=不改；base_url/model 明文存。
    写后立即 load_keys 注入 os.environ 生效，不重启。"""
    require_admin(request)
    updates: dict = {}

    def _apply(prefix: str, ku: Optional[KeyProviderUpdate]) -> None:
        if not ku:
            return
        if ku.key is not None:
            updates[f"{prefix}_API_KEY"] = ku.key
        if ku.base_url is not None:
            updates[f"{prefix}_BASE_URL"] = ku.base_url
        if ku.model is not None:
            updates[f"{prefix}_MODEL"] = ku.model

    _apply("OPENAI", body.deepseek)
    _apply("ARK", body.ark)
    _apply("MLAMP", body.mlamp)
    if not updates:
        raise HTTPException(400, "未提供可更新字段")
    settings_store.save_keys(updates)
    config.load_keys()  # 立即注入 os.environ 生效
    return {"ok": True}
