"""
Browser Use Cloud API 反向代理 + key 池轮换

上游: https://api.browser-use.com/api/v4
认证: X-Browser-Use-API-Key (bu_ 开头)

功能:
- 透明转发任意 方法/路径/查询 到上游 (含 SSE 流式响应)
- keys.txt 里的 key 轮询使用, 401/402/403/429 自动冷却并换下一个重试
- 支持运行中热更新 keys.txt (每行一个 key, # 开头为注释)
- 可选 PROXY_TOKEN 保护代理本身 (公网部署强烈建议开启)
"""

import asyncio
import os
import time

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

UPSTREAM = os.getenv("UPSTREAM", "https://api.browser-use.com").rstrip("/")
KEY_FILE = os.getenv("KEY_FILE", "keys.txt")
PROXY_TOKEN = os.getenv("PROXY_TOKEN", "")      # 设置后客户端必须带 Authorization: Bearer <token>
AUTH_MODE = os.getenv("AUTH_MODE", "pool")      # pool=强制用池子里的key | passthrough=客户端带了key就透传
MAX_TRIES = int(os.getenv("MAX_TRIES", "10"))   # 单次请求最多换几个 key 重试
PORT = int(os.getenv("PORT", "8787"))

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length",
}


class KeyPool:
    def __init__(self, path: str):
        self.path = path
        self.cooldown: dict[str, float] = {}
        self._i = 0
        self._lock = asyncio.Lock()
        self.keys: list[str] = []
        self.reload()

    def reload(self):
        self.keys = []
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.keys.append(line)

    async def acquire(self) -> str | None:
        async with self._lock:
            self.reload()  # 热更新, 改完 keys.txt 不用重启
            now = time.time()
            for _ in range(len(self.keys)):
                key = self.keys[self._i % len(self.keys)]
                self._i += 1
                if self.cooldown.get(key, 0) <= now:
                    return key
        return None

    def punish(self, key: str, seconds: float):
        self.cooldown[key] = time.time() + seconds

    def stats(self) -> dict:
        now = time.time()
        active = sum(1 for k in self.keys if self.cooldown.get(k, 0) <= now)
        return {"total": len(self.keys), "active": active, "cooling": len(self.keys) - active}


pool = KeyPool(KEY_FILE)
client = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30), follow_redirects=False)


def mask(key: str) -> str:
    return key[:6] + "..." + key[-4:] if len(key) > 12 else "***"


async def stream_body(resp: httpx.Response):
    try:
        async for chunk in resp.aiter_raw():
            yield chunk
    finally:
        await resp.aclose()


async def health(request: Request):
    return JSONResponse({"upstream": UPSTREAM, "auth_mode": AUTH_MODE, "pool": pool.stats()})


async def proxy(request: Request):
    if PROXY_TOKEN and request.headers.get("authorization") != f"Bearer {PROXY_TOKEN}":
        return JSONResponse({"error": "invalid proxy token"}, status_code=401)

    body = await request.body()
    last_status = 502

    for _ in range(MAX_TRIES):
        key = await pool.acquire()
        if key is None:
            break

        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}
        client_key = request.headers.get("x-browser-use-api-key")
        if AUTH_MODE == "pool" or not client_key:
            headers["X-Browser-Use-API-Key"] = key

        url = UPSTREAM + request.url.path
        if request.url.query:
            url += "?" + request.url.query

        try:
            req = client.build_request(request.method, url, headers=headers, content=body)
            resp = await client.send(req, stream=True)
        except httpx.HTTPError as e:
            print(f"[proxy] upstream connect failed: {e}")
            last_status = 502
            continue

        if resp.status_code in (401, 402, 403, 429):
            await resp.aread()
            await resp.aclose()
            pool.punish(key, 60 if resp.status_code == 429 else 300)
            print(f"[pool] key {mask(key)} -> {resp.status_code}, cooldown")
            last_status = resp.status_code
            continue

        resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in HOP_BY_HOP}
        return StreamingResponse(stream_body(resp), status_code=resp.status_code, headers=resp_headers)

    return JSONResponse({"error": "all keys unavailable or retries exhausted"}, status_code=last_status)


app = Starlette(routes=[
    Route("/health", health, methods=["GET"]),
    Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),
])

if __name__ == "__main__":
    print(f"listening on 0.0.0.0:{PORT}  upstream={UPSTREAM}  mode={AUTH_MODE}  keys={len(pool.keys)}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
