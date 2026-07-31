@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Browser Use Proxy

if not exist keys.txt copy keys.example.txt keys.txt >nul

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://www.python.org/downloads/
    echo         Remember to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

python -c "import httpx, starlette, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo First run: installing dependencies...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] pip install failed. Check network and retry.
        pause
        exit /b 1
    )
)

type keys.txt | findstr /r "^bu_" | findstr /v /i "xxxx" >nul
if errorlevel 1 (
    echo [SETUP] Notepad will open. Paste your keys, SAVE, then CLOSE notepad to continue.
    start /wait notepad keys.txt
)

echo.
echo ============================================================
echo   Proxy: http://127.0.0.1:8787   Health: /health
echo   Minimize this window. Closing it STOPS the proxy.
echo ============================================================
echo.
python proxy.py
pause
