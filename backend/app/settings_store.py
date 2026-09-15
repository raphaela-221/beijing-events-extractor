"""持久化运行设置到 config/settings.json（gitignored）。

红线遵守：不碰 .env（LLM key 只读自 .env）、不加 DB 表（避开 schema 红线）。
只存运行时配置：回收站保留天数 / canonical .bak 保留份数 / 上次自检 / 上次清理摘要。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import config

SETTINGS_PATH = config.CONFIG_DIR / "settings.json"

DEFAULTS = {
    "retention_days": 30,  # 回收站保留天数，超期自动 purge（与 store.TRASH_RETENTION_DAYS 一致）
    "canonical_bak_keep": 10,  # canonical .bak 保留份数，超出按 mtime 删最旧
    "share_path": None,  # 对外分享别名路径（发布页可改）；None=用 .env/默认，'-'=关闭
    "last_selfcheck": None,  # {at, ok, block_count, warn_count, checks}
    "last_cleanup": None,  # {at, purged_runs, deleted_baks, freed_bytes, orphans}
}


def load() -> dict:
    """读设置，缺字段用默认补齐。文件不存在或损坏返回默认。"""
    data = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            data.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    # 类型兜底，防止手改出非 int
    for k in ("retention_days", "canonical_bak_keep"):
        try:
            data[k] = int(data.get(k, DEFAULTS[k]))
        except (TypeError, ValueError):
            data[k] = DEFAULTS[k]
    # share_path 兜底为 str|None（去掉首尾斜杠）
    sp = data.get("share_path")
    data["share_path"] = sp.strip().strip("/") if isinstance(sp, str) and sp.strip() else None
    return data


def effective_share_path() -> str:
    """对外分享别名路径（唯一取值口径，main.py 挂载 / publish.py 展示都用它）：
    settings.json（发布页可改）优先，None 回退 .env EXTERNAL_SHARE_PATH（默认
    beijing-events-calendar）。返回 '-' 表示关闭（回退 /preview 直链）。"""
    p = load().get("share_path")
    return p if p else config.EXTERNAL_SHARE_PATH


def save(updates: dict) -> dict:
    """合并写：读当前 -> 合并 updates -> 原子写。返回写后全量。"""
    data = load()
    data.update(updates)
    _atomic_write(SETTINGS_PATH, json.dumps(data, ensure_ascii=False, indent=2))
    return data


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ---- LLM keys（config/llm_keys.json，gitignored；不碰 .env）----
KEYS_PATH = config.CONFIG_DIR / "llm_keys.json"

# base_url/model 默认值（与 .env.example 一致）；key 字段无默认（敏感）
KEY_DEFAULTS = {
    "OPENAI_BASE_URL": "https://api.deepseek.com/v1",
    "OPENAI_MODEL": "deepseek-v4-flash",
    "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/plan",
    "ARK_MODEL": "deepseek-v4-flash",
    "MLAMP_BASE_URL": "https://llmgw-bz.mlamp.cn/v1/chat/completions",
    "MLAMP_MODEL": "deepseek-v4.1-flash",
}


def load_keys() -> dict:
    """读 llm_keys.json，base_url/model 缺字段用默认补。"""
    data = {}
    if KEYS_PATH.exists():
        try:
            data = json.loads(KEYS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    for k, v in KEY_DEFAULTS.items():
        data.setdefault(k, v)
    return data


def save_keys(updates: dict) -> dict:
    """合并写 keys。"""
    data = load_keys()
    data.update(updates)
    _atomic_write(KEYS_PATH, json.dumps(data, ensure_ascii=False, indent=2))
    return data


def mask_key(v: str) -> str:
    """key 遮罩，只回显首2+末4，供前端展示已配置状态。"""
    if not v:
        return ""
    if len(v) <= 8:
        return "****"
    return v[:2] + "..." + v[-4:]
