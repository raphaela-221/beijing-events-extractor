@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

if not exist "%ROOT%\frontend\dist\index.html" (
  echo 错误：frontend\dist 不存在。先构建前端：
  echo   cd frontend ^&^& npm run build
  pause
  exit /b 1
)

:: Pick Python: py launcher first, then python; skip Microsoft Store stub
set "PYTHON_PATH="
for %%C in (py python) do (
    if not defined PYTHON_PATH (
        %%C -c "print(1)" >nul 2>&1 && set "PYTHON_PATH=%%C"
    )
)
if not defined PYTHON_PATH (
    echo 错误：找不到可用的 Python。请确认已安装 Python 3.10+ 及项目依赖
    echo （pip install -r requirements.txt，或使用离线包内置 python\python.exe）。
    echo 注意：Windows 自带的 Microsoft Store "python" 不是真 Python，跑不了代码。
    pause
    exit /b 1
)

if "%CONSOLE_PORT%"=="" set "CONSOLE_PORT=8000"

echo 启动操作台后端（生产模式，0.0.0.0:%CONSOLE_PORT%）...
echo 浏览器访问 http://localhost:%CONSOLE_PORT% 或 http://本机IP:%CONSOLE_PORT%
cd /d "%ROOT%\backend"
"%PYTHON_PATH%" -m uvicorn app.main:app --host 0.0.0.0 --port %CONSOLE_PORT%
pause
