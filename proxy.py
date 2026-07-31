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
import json
import os
import time

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
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


async def index(request: Request):
    """根路径说明页, 避免访问 / 看到上游的 404 以为出错"""
    s = pool.stats()
    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>BU 反代</title>
<style>body{{font-family:"Microsoft YaHei",system-ui,sans-serif;background:#f3f5f7;display:flex;justify-content:center;padding-top:60px}}
.card{{background:#fff;border-radius:14px;padding:32px 40px;box-shadow:0 2px 10px rgba(0,0,0,.08);max-width:520px}}
h1{{font-size:20px}} .ok{{color:#16a34a}} li{{margin:8px 0;font-size:15px}} a{{color:#2563eb}}</style></head>
<body><div class="card">
<h1>✅ 反代运行中 <span class="ok">(这不是错误页面)</span></h1>
<p>上游: {UPSTREAM} · key 池: 共 {s['total']} 个, 当前可用 {s['active']} 个</p>
<ul>
<li><a href="/health">/health</a> — key 池状态 (JSON)</li>
<li><a href="/v1/models">/v1/models</a> — OpenAI 兼容模型列表</li>
<li>/api/v4/... — 透明转发到官方 API (给程序用)</li>
</ul>
<p>日常用请直接双击 <b>task-panel.html</b> 打开图形面板。</p>
</div></body></html>"""
    from starlette.responses import HTMLResponse
    return HTMLResponse(html)


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


# ---------- OpenAI 兼容适配层 (转接层) ----------
# 把 /v1/chat/completions 包装成 Browser Use 的 agent run, 让 opencode/ChatBox 等工具能用

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "grok-4.5")  # 官方文档推荐的性价比款
CHAT_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "600"))    # 单次对话最长等多久(秒), agent 跑得慢
VALID_MODELS = [
    "glm-5.2", "grok-4.5", "kimi-k3", "minimax-m3",
    "claude-opus-4.7", "claude-opus-4.8", "claude-opus-5", "claude-fable-5", "claude-sonnet-5",
    "gpt-5.5", "gpt-5.6",
    "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.1-pro", "gemini-3-flash",
]

CHAT_PREAMBLE = (
    "You are answering a chat conversation from an API client. "
    "Do NOT browse the web unless the request truly requires it. "
    "Answer directly and return only the final reply text.\n\n"
)


def flatten_messages(messages: list) -> str:
    parts = []
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, list):  # OpenAI 多段格式
            content = "\n".join(p.get("text", "") for p in content
                                if isinstance(p, dict) and p.get("type") == "text")
        parts.append(f"[{m.get('role', 'user').capitalize()}]\n{content}")
    return CHAT_PREAMBLE + "\n\n".join(parts)


async def upstream_json(method: str, path: str, key: str, body: dict | None = None) -> httpx.Response:
    return await client.request(method, UPSTREAM + path,
                                headers={"X-Browser-Use-API-Key": key}, json=body)


async def run_as_chat(task_text: str, model: str) -> tuple[str, dict]:
    """创建 run 并轮询到结束, 返回 (结果文本, 完整run数据)"""
    last_err = "no available key"
    for _ in range(MAX_TRIES):
        key = await pool.acquire()
        if key is None:
            break
        r = await upstream_json("POST", "/api/v4/runs", key, {"task": task_text, "model": model})
        if r.status_code in (401, 402, 403, 429):
            pool.punish(key, 60 if r.status_code == 429 else 300)
            print(f"[pool] key {mask(key)} -> {r.status_code}, cooldown")
            last_err = f"key rejected: {r.status_code}"
            continue
        if r.status_code != 200:
            last_err = f"create run failed {r.status_code}: {r.text[:300]}"
            continue

        run_id = r.json()["id"]
        deadline = time.time() + CHAT_TIMEOUT
        status = "queued"
        while time.time() < deadline:
            await asyncio.sleep(3)
            s = await upstream_json("GET", f"/api/v4/runs/{run_id}/status", key)
            status = s.json().get("status", "")
            if status in ("completed", "failed", "cancelled"):
                break

        full = await upstream_json("GET", f"/api/v4/runs/{run_id}", key)
        data = full.json()
        if data.get("status") == "completed" and data.get("result"):
            return data["result"], data
        last_err = data.get("error") or f"run ended with status: {status}"
        break  # run 级别的失败与 key 无关, 不重试
    raise RuntimeError(last_err)


async def list_models(request: Request):
    return JSONResponse({"object": "list", "data": [
        {"id": m, "object": "model", "created": 0, "owned_by": "browser-use"} for m in VALID_MODELS
    ]})


async def chat_completions(request: Request):
    if PROXY_TOKEN and request.headers.get("authorization") != f"Bearer {PROXY_TOKEN}":
        return JSONResponse({"error": {"message": "invalid proxy token"}}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": {"message": "invalid JSON body"}}, status_code=400)

    messages = body.get("messages") or []
    if not messages:
        return JSONResponse({"error": {"message": "messages is required"}}, status_code=400)
    model = body.get("model") or DEFAULT_MODEL
    if model not in VALID_MODELS:
        model = DEFAULT_MODEL

    try:
        result, meta = await run_as_chat(flatten_messages(messages), model)
    except RuntimeError as e:
        return JSONResponse({"error": {"message": str(e), "type": "server_error"}}, status_code=502)

    cid = "chatcmpl-" + meta.get("id", "x").replace("-", "")[:24]
    created = int(time.time())
    usage = {
        "prompt_tokens": meta.get("totalInputTokens") or 0,
        "completion_tokens": meta.get("totalOutputTokens") or 0,
        "total_tokens": (meta.get("totalInputTokens") or 0) + (meta.get("totalOutputTokens") or 0),
    }

    if body.get("stream"):
        async def sse():
            yield f'data: {{"id":"{cid}","object":"chat.completion.chunk","created":{created},"model":"{model}","choices":[{{"index":0,"delta":{{"role":"assistant","content":{json.dumps(result)}}},"finish_reason":null}}]}}\n\n'
            yield f'data: {{"id":"{cid}","object":"chat.completion.chunk","created":{created},"model":"{model}","choices":[{{"index":0,"delta":{{}},"finish_reason":"stop"}}]}}\n\n'
            yield "data: [DONE]\n\n"
        return StreamingResponse(sse(), media_type="text/event-stream")

    return JSONResponse({
        "id": cid, "object": "chat.completion", "created": created, "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": result}, "finish_reason": "stop"}],
        "usage": usage,
    })


app = Starlette(
    routes=[
        Route("/", index, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/v1/models", list_models, methods=["GET"]),
        Route("/v1/chat/completions", chat_completions, methods=["POST"]),
        Route("/{path:path}", proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),
    ],
    # 允许本地面板(file:// 打开的 task-panel.html)等网页直接调用
    middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
)

if __name__ == "__main__":
    print(f"listening on 0.0.0.0:{PORT}  upstream={UPSTREAM}  mode={AUTH_MODE}  keys={len(pool.keys)}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
