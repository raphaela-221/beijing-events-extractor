"""集中管理路径与配置。

红线遵守：绝不写 .env（LLM key 与 session secret 分开存放）。
- LLM key 由 main.py 自己从项目根 .env 读（子进程继承）。
- session secret 自动生成到 config/session_secret（gitignored）。
- 账号哈希在 config/users.json（gitignored）。
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> parents[2] = 项目根
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"

# ---- 现有 pipeline ----
STEP1_MAIN = PROJECT_ROOT / "01_event_extractor" / "main.py"
ENRICH_DATES_MAIN = PROJECT_ROOT / "01_event_extractor" / "enrich_concert_dates.py"
CANONICAL_PATH = PROJECT_ROOT / "01_event_list_output" / "Events List.xlsx"
CALENDAR_DIR = PROJECT_ROOT / "02_calendar"
WEB_OUTPUT_DIR = PROJECT_ROOT / "02_web_output"

# ---- 运行时数据（gitignored）----
DATA_DIR = PROJECT_ROOT / "data"
RUNS_DIR = DATA_DIR / "runs"
CANONICAL_BACKUPS_DIR = DATA_DIR / "canonical" / "backups"
UPLOADS_DIR = DATA_DIR / "uploads"
PUBLISHES_DIR = DATA_DIR / "publishes"
DB_PATH = DATA_DIR / "console.db"

# ---- 密钥 / 账号（gitignored）----
CONFIG_DIR = PROJECT_ROOT / "config"
USERS_PATH = CONFIG_DIR / "users.json"
SESSION_SECRET_PATH = CONFIG_DIR / "session_secret"

# ---- dev CORS（Vite dev server）----
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# ---- 发布配置（从 env 读，留空降级；红线：绝不写 .env）----
EXTERNAL_SHARE_URL = os.getenv("EXTERNAL_SHARE_URL", "").strip()
PLATFORM_UPLOAD_URL = os.getenv("PLATFORM_UPLOAD_URL", "").strip()
# 对外分享别名路径：把日历以 /<路径名>/ 挂到本端口（main.py 挂载）。
# 默认 beijing-events-calendar；.env 里填 - 可关闭，填其他名字可改。
EXTERNAL_SHARE_PATH = os.getenv("EXTERNAL_SHARE_PATH", "beijing-events-calendar").strip().strip("/")


def ensure_dirs() -> None:
    for d in (DATA_DIR, RUNS_DIR, CANONICAL_BACKUPS_DIR, UPLOADS_DIR, PUBLISHES_DIR, CONFIG_DIR, WEB_OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    """加载项目根 .env（LLM key），供后端 preflight env_keys 检查读取。"""
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


def load_keys() -> None:
    """读 config/llm_keys.json 注入 os.environ（覆盖 .env），让 os.getenv 读到。
    不碰 .env（红线）。启动时 + 改 key 后调。优先级：llm_keys.json > .env。"""
    p = CONFIG_DIR / "llm_keys.json"
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    for k, v in data.items():
        if isinstance(v, str) and v:
            os.environ[k] = v


def get_session_secret() -> str:
    """持久化随机 session secret 到 config/session_secret（gitignored）。
    不碰 .env（红线）。首次生成，之后跨重启复用，登录态不因重启丢失。"""
    if SESSION_SECRET_PATH.exists():
        return SESSION_SECRET_PATH.read_text(encoding="utf-8").strip()
    ensure_dirs()
    secret = secrets.token_urlsafe(48)
    SESSION_SECRET_PATH.write_text(secret, encoding="utf-8")
    return secret


# 模块导入时加载 .env，使 preflight 能读到 key 状态
load_env()
