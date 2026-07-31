@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Browser Use Proxy - 关闭此窗口即停止

if not exist keys.txt copy keys.example.txt keys.txt >nul

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://www.python.org/downloads/
    echo         An zhuang shi ji de gou xuan "Add Python to PATH"
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
    echo [WARN] keys.txt has no real key yet. Opening it in notepad...
    notepad keys.txt
)

echo.
echo ============================================================
echo   Proxy: http://127.0.0.1:8787   Health: /health
echo   Minimize this window. Closing it STOPS the proxy.
echo ============================================================
echo.
python proxy.py
pause
