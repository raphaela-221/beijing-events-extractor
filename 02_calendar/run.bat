@echo off
chcp 65001 >nul
:: Windows entry point for Step 2: canonical Events List.xlsx → calendar website.
:: Usage:
::   run.bat                                     use ..\01_event_list_output\Events List.xlsx
::   run.bat "path\to\file.xlsx"                 use a specific source Excel

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "EVENT_LIST_DIR=%SCRIPT_DIR%\..\01_event_list_output"
set "CANONICAL_SOURCE=%EVENT_LIST_DIR%\Events List.xlsx"

:: Use PYTHON_PATH if passed from the top-level launcher, otherwise detect.
if not defined PYTHON_PATH (
    set "PYTHON_PATH="
    for %%C in (py python) do (
        if not defined PYTHON_PATH (
            %%C -c "print(1)" >nul 2>&1 && set "PYTHON_PATH=%%C"
        )
    )
    if not defined PYTHON_PATH (
        echo 错误：找不到可用的 Python。请先运行根目录的 setup.bat。
        echo 注意：Windows 自带的 Microsoft Store "python" 不是真 Python，跑不了代码。
        pause
        exit /b 1
    )
)

:: Determine source Excel
set "SOURCE=%~1"
if "%SOURCE%"=="" set "SOURCE=%CANONICAL_SOURCE%"

if not exist "%SOURCE%" (
    echo 错误：找不到源 Excel: %SOURCE%
    echo 请先确认 01_event_list_output\Events List.xlsx 存在，或传入自定义路径。
    pause
    exit /b 1
)

echo 源文件: %SOURCE%
echo.

echo [1/4] Extracting High events from source Excel...
"%PYTHON_PATH%" "%SCRIPT_DIR%\run_pipeline.py" extract --source "%SOURCE%"
if %errorlevel% neq 0 (
    echo Extract failed.
    pause
    exit /b 1
)

echo.
echo [2/4] Generating/enriching monthly themes (incremental)...
"%PYTHON_PATH%" "%SCRIPT_DIR%\run_pipeline.py" themes --year 2026
if %errorlevel% neq 0 (
    echo Theme enrichment skipped or failed. You can re-run it later with:
    echo   python run_pipeline.py themes --year 2026
)

echo.
echo [3/4] Verifying calendar pages...
"%PYTHON_PATH%" "%SCRIPT_DIR%\run_pipeline.py" calendar

echo.
echo [4/4] Packaging viewer-facing files for sharing...
"%PYTHON_PATH%" "%SCRIPT_DIR%\run_pipeline.py" package

echo.
echo Pipeline finished.
echo   - Open index.html to preview.
echo   - Upload the 02_web_output/ folder to OneDrive and share the folder link.
pause
