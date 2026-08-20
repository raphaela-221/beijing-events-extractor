@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

"%ROOT%\python\python.exe" "%ROOT%\deployment\start_server.py"
pause
