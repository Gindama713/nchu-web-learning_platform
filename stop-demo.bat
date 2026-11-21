@echo off
chcp 65001 >nul
title Demo Week11 - stop
cd /d "%~dp0"
"D:\Desktop\WebBigHomework(5)\WebBigHomework\.venv\Scripts\python.exe" "%~dp0demo-launcher.py" --stop
echo.
timeout /t 6 >nul
