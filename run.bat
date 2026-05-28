@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

REM 设置 embedded Python 路径
set PYTHON_PATH=%~dp0python\python.exe

REM 把项目根目录加入 Python 模块搜索路径
set PYTHONPATH=%~dp0

REM 运行主程序，并把所有参数传过去
%PYTHON_PATH% %~dp0main.py %*

pause
