#!/bin/bash
# 一键打开北京大事件操作台（Mac 双击）。
# 自动启动操作台后端（serve frontend/dist，端口 8000），并在就绪后打开浏览器。
# 关掉终端窗口即停止服务（与 run_console.sh 相同，不做后台守护进程）。
cd "$(dirname "$0")"

# 前置检查：frontend/dist 是否存在（不存在会直接报错，避免起了个空壳）
if [ ! -f "frontend/dist/index.html" ]; then
  echo "错误：frontend/dist 不存在。先构建前端：cd frontend && npm run build"
  read -r -p "按回车关闭..." _
  exit 1
fi

PORT="${CONSOLE_PORT:-8000}"

# 后台起服务，主线程负责开浏览器（避免浏览器先开抢在服务就绪前）
# 用 bash 显式执行，不依赖 run_console.sh 自身的执行权限
bash run_console.sh &
SERVER_PID=$!

# 等后端就绪（最多 15 秒），就绪后自动打开浏览器
for _ in $(seq 1 30); do
  if curl -s -o /dev/null "http://localhost:${PORT}/api/health"; then
    echo "操作台已就绪，打开浏览器：http://localhost:${PORT}"
    open "http://localhost:${PORT}"
    break
  fi
  sleep 0.5
done

# 把终端窗口交还给后端进程（Ctrl+C 或关窗口即停服务）
wait "${SERVER_PID}"
