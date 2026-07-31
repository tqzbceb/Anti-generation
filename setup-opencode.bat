@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Setup opencode config

echo Checking proxy...
curl -s -m 3 http://127.0.0.1:8787/health >nul 2>nul
if errorlevel 1 (
    echo [WARN] Proxy not running. Start it first: double-click start-windows.bat
    echo        You can still run this setup, but the model will not work until proxy is up.
    echo.
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-opencode.ps1"
echo.
pause
