#!/usr/bin/env bash
# 生产模式启动操作台后端：serve frontend/dist，单端口绑 0.0.0.0。
# 前置：frontend/dist 必须存在（先 cd frontend && npm run build）。
# dev 模式请用 vite + uvicorn --reload（见开发指南），不要跑这个。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST="$ROOT/frontend/dist"
if [ ! -f "$DIST/index.html" ]; then
  echo "错误：frontend/dist 不存在。先构建前端：cd frontend && npm run build"
  exit 1
fi
PORT="${CONSOLE_PORT:-8000}"
echo "启动操作台后端（生产模式，0.0.0.0:${PORT}）..."
echo "浏览器访问 http://localhost:${PORT} 或 http://本机IP:${PORT}"
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
