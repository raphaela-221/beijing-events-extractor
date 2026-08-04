@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

:: Pick Python: system python first, then py launcher
where python >nul 2>nul
if %errorlevel% == 0 (
    set "PYTHON_PATH=python"
) else (
    where py >nul 2>nul
    if %errorlevel% == 0 (
        set "PYTHON_PATH=py"
    ) else (
        echo 错误：找不到 Python。请安装 Python 3.10+ 并加到 PATH。
        pause
        exit /b 1
    )
)

echo 使用 Python: %PYTHON_PATH%
echo.

echo [1/2] 安装 Python 依赖...
"%PYTHON_PATH%" -m pip install -r "%ROOT%\requirements.txt"
if %errorlevel% neq 0 (
    echo 依赖安装失败。
    pause
    exit /b 1
)

echo.
echo [2/2] 安装 Playwright Chromium（演唱会采集需要）...
"%PYTHON_PATH%" -m playwright install chromium
if %errorlevel% neq 0 (
    echo Playwright 安装失败。演唱会采集可能不可用。
    pause
    exit /b 1
)

echo.
echo 完成。现在可以运行 run.bat 选择步骤 1 或步骤 2。
echo.
echo 注意：运行步骤 1 前，请把 .env.example 复制为 .env，并填写 ARK_API_KEY。
echo   copy .env.example .env
pause
