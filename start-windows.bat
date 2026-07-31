@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Browser Use Proxy

if not exist keys.txt copy keys.example.txt keys.txt >nul

rem Port 8787 already occupied = an old instance is still running.
rem Kill it and restart fresh (double-click = restart with latest keys.txt).
netstat -ano | findstr ":8787 " | findstr LISTENING >nul
if not errorlevel 1 (
    echo [INFO] Port 8787 already in use - an old proxy instance is running.
    echo        Stopping it and restarting with your current keys.txt ...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8787 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>nul
    timeout /t 2 /nobreak >nul
)

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
