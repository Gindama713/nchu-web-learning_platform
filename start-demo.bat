@echo off
chcp 65001 >nul
title Demo Week11 - start
cd /d "%~dp0"
echo Starting backend 5000 + frontend 5173 ...
echo.
"D:\Desktop\WebBigHomework(5)\WebBigHomework\.venv\Scripts\python.exe" "%~dp0demo-launcher.py"
echo.
echo Done. Keep this window or close it - services run detached.
timeout /t 8 >nul
