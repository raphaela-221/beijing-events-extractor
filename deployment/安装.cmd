@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo ============================================
echo   北京大事件操作台 - 安装
echo ============================================
echo 安装目录: %ROOT%
echo.

echo [1/2] 初始化配置（选端口）...
"%ROOT%\python\python.exe" "%ROOT%\deployment\init_install.py"
if %errorlevel% neq 0 (
  echo 初始化失败。
  pause
  exit /b 1
)
echo.

echo [2/2] 创建启动项...
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
> "%STARTUP%\beijing-events-console.cmd" echo @echo off
>> "%STARTUP%\beijing-events-console.cmd" echo cd /d "%ROOT%"
>> "%STARTUP%\beijing-events-console.cmd" echo call "%ROOT%\run.cmd"
>> "%STARTUP%\beijing-events-console.cmd" echo pause
echo 已创建启动项: %STARTUP%\beijing-events-console.cmd
echo.

echo ============================================
echo 安装完成！双击 run.cmd 启动（或重启自动启动）。
echo ============================================
pause
