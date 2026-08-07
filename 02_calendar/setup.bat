@echo off
chcp 65001 >nul
:: 一次性安装 Python 依赖 (02_calendar 独立 installer；通常用根目录 setup.bat 即可)
:: One-time dependency installer for Windows

REM --- Detect real Python, skip Microsoft Store stub ---
set "PYTHON_PATH="
for %%C in (py python) do (
    if not defined PYTHON_PATH (
        %%C -c "print(1)" >nul 2>&1 && set "PYTHON_PATH=%%C"
    )
)
if not defined PYTHON_PATH (
    echo [ERROR] No usable Python found.
    echo Install Python 3.10+ from https://www.python.org/downloads/ and check "Add Python to PATH".
    echo Note: the Microsoft Store "python" is a stub and cannot run code.
    pause
    exit /b 1
)

echo Installing dependencies...
"%PYTHON_PATH%" -m pip install --user openpyxl requests urllib3

if %errorlevel% neq 0 (
    echo Failed to install dependencies. Make sure Python is installed and on PATH.
    pause
    exit /b 1
)

echo Done. You can now run run.bat.
pause
