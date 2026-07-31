#!/bin/bash
# Browser Use Proxy launcher - double click to run. Closing window stops proxy.
cd "$(dirname "$0")"

[ -f keys.txt ] || cp keys.example.txt keys.txt

if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] python3 not found. Install from https://www.python.org/downloads/"
    read -r
    exit 1
fi

if ! python3 -c "import httpx, starlette, uvicorn" 2>/dev/null; then
    echo "First run: installing dependencies..."
    python3 -m pip install --user -r requirements.txt || {
        echo "[ERROR] pip install failed. Check network and retry."
        read -r
        exit 1
    }
fi

if ! grep "^bu_" keys.txt | grep -qv "xxxx"; then
    echo "[SETUP] Editor will open. Paste your keys, SAVE, then CLOSE it to continue."
    open -W -e keys.txt 2>/dev/null
fi

echo ""
echo "============================================================"
echo "  Proxy: http://127.0.0.1:8787   Health: /health"
echo "  Minimize this window. Closing it STOPS the proxy."
echo "============================================================"
echo ""
python3 proxy.py
