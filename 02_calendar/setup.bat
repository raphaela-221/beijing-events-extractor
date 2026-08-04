@echo off
chcp 65001 >nul
:: 一次性安装 Python 依赖
:: One-time dependency installer for Windows

echo Installing dependencies...
python -m pip install --user openpyxl requests urllib3

if %errorlevel% neq 0 (
    echo Failed to install dependencies. Make sure Python is installed and on PATH.
    pause
    exit /b 1
)

echo Done. You can now run run.bat.
pause
