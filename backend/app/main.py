"""FastAPI 应用入口。P0 先放 /api/health + 启动钩子（建表 + 孤儿修复），
路由在后续 task 中挂载。"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Mount

from . import auth, config, db, maintenance, settings_store
from .routes import canonical as canonical_routes
from .routes import jobs as job_routes
from .routes import lock as lock_routes
from .routes import pipeline as pipeline_routes
from .routes import publish as publish_routes
from .routes import runs as run_routes
from .routes import settings as settings_routes
from .routes import upload as upload_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("console")


async def _startup_selfcheck() -> None:
    """启动 60s 后跑一次自检，结果写 settings.json + cleanup_log.jsonl。"""
    await asyncio.sleep(60)
    try:
        await asyncio.to_thread(maintenance.selfcheck)
        logger.info("启动自检完成")
    except Exception as e:  # noqa: BLE001 后台任务不应崩
        logger.warning("启动自检失败: %s", e)


async def _daily_cleanup() -> None:
    """每日 03:00 跑自动清理（回收站超期/.bak 超份/孤儿目录），循环。"""
    while True:
        now = datetime.now()
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run + timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            res = await asyncio.to_thread(maintenance.auto_cleanup)
            logger.info(
                "每日清理完成: purge=%d bak=%d orphan=%d freed=%d",
                res["purged_runs"], res["deleted_baks"], res["orphans"], res["freed_bytes"],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("每日清理失败: %s", e)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_dirs()
    config.load_keys()  # 注入 llm_keys.json 到 os.environ（覆盖 .env），preflight 能读到
    db.init_db()
    n = db.recover_orphans()
    if n:
        logger.info("恢复 %d 个中断任务 -> failed/interrupted", n)
    auth.seed_users_if_empty()
    # 后台调度：60s 自检 + 每日 03:00 清理（to_thread 避免阻塞 event loop）
    bg_tasks = [
        asyncio.create_task(_startup_selfcheck()),
        asyncio.create_task(_daily_cleanup()),
    ]
    logger.info("后端就绪，db=%s", config.DB_PATH)
    yield
    for t in bg_tasks:
        t.cancel()


app = FastAPI(title="北京大事件操作台", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=config.get_session_secret(),
    session_cookie="console_session",
    same_site="lax",
    https_only=False,  # 局域网 http
    max_age=60 * 60 * 12,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(lock_routes.router)
app.include_router(job_routes.router)
app.include_router(run_routes.router)
app.include_router(upload_routes.router)
app.include_router(pipeline_routes.router)
app.include_router(canonical_routes.router)
app.include_router(publish_routes.router)
app.include_router(settings_routes.router)

# 内置预览：托管 02_web_output/（指南 §6；Vite dev 已配 /preview proxy）。
# mount 前确保目录存在（首次启动时 lifespan 的 ensure_dirs 尚未执行）。
config.WEB_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/preview", StaticFiles(directory=str(config.WEB_OUTPUT_DIR), html=True), name="preview")

# 对外分享别名：把同一份日历以 /<路径名>/ 挂到本端口（免登录），
# 同事直接访问形如 http://主机:端口/beijing-events-calendar/，不必依赖 8080 平台。
# 路径名在「预览与发布」页可改（settings.json，admin），改完热生效，不用重启；
# .env 的 EXTERNAL_SHARE_PATH 只是页面没改过时的默认值。
def apply_external_share_mount() -> None:
    """按 effective_share_path() 重挂别名 mount。幂等：先移除旧的再插新的。
    必须插到 SPA catch-all（name='spa'）之前，否则会被吞掉。"""
    slug = settings_store.effective_share_path()
    app.router.routes = [r for r in app.router.routes if getattr(r, "name", "") != "external-share"]
    if not slug or slug == "-":
        return
    mount = Mount(
        f"/{slug}",
        app=StaticFiles(directory=str(config.WEB_OUTPUT_DIR), html=True),
        name="external-share",
    )
    idx = next(
        (i for i, r in enumerate(app.router.routes) if getattr(r, "name", "") == "spa"),
        len(app.router.routes),
    )
    app.router.routes.insert(idx, mount)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


# 生产模式：serve frontend/dist（单端口，脱离 Vite dev）。
# dev 模式（CONSOLE_DEV=1）跳过，留给 Vite :5173 + proxy。
# catch-all 必须在所有 /api 路由 + /preview mount 之后注册，避免吞掉 API。
FRONTEND_DIST = config.PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST.exists() and os.getenv("CONSOLE_DEV") != "1":
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = (FRONTEND_DIST / full_path).resolve()
        try:
            target.relative_to(FRONTEND_DIST.resolve())
        except ValueError:
            # 路径穿越尝试 -> 回退 index.html
            return FileResponse(FRONTEND_DIST / "index.html")
        if target.is_file():
            return FileResponse(target)
        # SPA fallback：React Router 路由刷新不 404
        return FileResponse(FRONTEND_DIST / "index.html")

# SPA catch-all 注册完再挂别名（保证插到它前面）。
apply_external_share_mount()
