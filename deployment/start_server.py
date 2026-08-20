"""读 config/service.json 拿端口，启动 uvicorn（serve frontend/dist）。Windows 上由 run.cmd 调用。

设 PLAYWRIGHT_BROWSERS_PATH 指向包内 browsers/（内置 Chromium），chdir 到 app/。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SJ = ROOT / "config" / "service.json"

port = 8000
if SJ.exists():
    try:
        port = json.loads(SJ.read_text(encoding="utf-8")).get("port") or 8000
    except Exception:
        pass

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / "browsers")

# 首次运行：chromium 不存在则 playwright install（需出站网络，一次性 ~150MB，之后离线）
rev = None
if SJ.exists():
    try:
        rev = json.loads(SJ.read_text(encoding="utf-8")).get("chromium_revision")
    except Exception:
        pass
chromium_dir = ROOT / "browsers" / f"chromium-{rev}" if rev else None
if not (chromium_dir and chromium_dir.exists()):
    import subprocess
    print("首次运行：下载 Chromium（约 150MB，需出站网络，之后离线）...")
    subprocess.run(
        [str(ROOT / "python" / "python.exe"), "-m", "playwright", "install", "chromium"],
        check=True,
    )

backend_dir = ROOT / "app" / "backend"
os.chdir(backend_dir)
sys.path.insert(0, str(backend_dir))

import uvicorn  # noqa: E402

print(f"启动操作台：http://0.0.0.0:{port}（浏览器访问 http://localhost:{port}）")
uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
