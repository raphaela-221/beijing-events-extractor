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
        echo 错误：找不到 Python。请先运行 setup.bat 安装 Python。
        pause
        exit /b 1
    )
)

:: Command-line mode: run.bat step1 [args...] / run.bat step2
if /I "%~1"=="step1" (
    set "ARGS=%*"
    set "ARGS=%ARGS:* =%"
    goto run_step1
)
if /I "%~1"=="step2" (
    goto run_step2
)

:: Interactive menu
:menu
echo.
echo ==============================
echo   北京大事件信息提取
echo ==============================
echo [1] 构建事件清单（Step 1）
echo [2] 生成日历看板（Step 2）
echo [0] 退出
echo.
choice /C 120 /N /M "请选择 [1/2/0]: "
if errorlevel 3 goto :eof
if errorlevel 2 goto run_step2
if errorlevel 1 goto run_step1

:run_step1
echo.
echo [Step 1] 从 01_raw_input/ 提取并增量合并事件清单...
"%PYTHON_PATH%" "%ROOT%\01_event_extractor\main.py" --concert %ARGS%
if %errorlevel% neq 0 (
    echo Step 1 运行失败。
    pause
    exit /b 1
)
echo.
echo Step 1 完成。输出在 01_event_list_output/。
echo 接下来可运行 run.bat step2 生成日历看板。
set "ARGS="
pause
exit /b 0

:run_step2
echo.
echo [Step 2] 生成日历看板...
call "%ROOT%\02_calendar\run.bat"
if %errorlevel% neq 0 (
    echo Step 2 运行失败。
    pause
    exit /b 1
)
echo.
echo Step 2 完成。分享包在 02_web_output/。
pause
exit /b 0
