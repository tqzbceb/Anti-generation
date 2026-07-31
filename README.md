# Browser Use Cloud API 反向代理（key 池版）

透明反代 `https://api.browser-use.com`，自动从 key 池轮换注入 `X-Browser-Use-API-Key`。
挂了（401/402/403）自动冷却 5 分钟，限流（429）冷却 1 分钟，自动换下一个重试。

## 快速开始

```bash
pip install -r requirements.txt
# 把 key 粘贴进 keys.txt（每行一个，支持热更新，改完不用重启）
python proxy.py
```

默认监听 `0.0.0.0:8787`。健康检查/池状态：`curl http://127.0.0.1:8787/health`

## 怎么用

把所有官方 API 地址 `https://api.browser-use.com` 换成 `http://你的机器:8787` 即可，
其他完全不变（路径、参数、认证头格式都一样）。pool 模式下 key 随便填，代理会用池子里的真 key 替换。

```bash
# 创建一个 v4 agent 任务
curl -X POST http://127.0.0.1:8787/api/v4/runs \
  -H "Content-Type: application/json" \
  -H "X-Browser-Use-API-Key: whatever" \
  -d '{"task":"打开 example.com 并告诉我标题"}'
```

Python SDK 用法：

```python
from browser_use_sdk import BrowserUse
client = BrowserUse(api_key="whatever", base_url="http://127.0.0.1:8787")
```

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `PORT` | `8787` | 监听端口 |
| `KEY_FILE` | `keys.txt` | key 池文件路径 |
| `AUTH_MODE` | `pool` | `pool`=强制用池子里的 key；`passthrough`=客户端带 key 就透传 |
| `PROXY_TOKEN` | 空 | 设置后客户端必须带 `Authorization: Bearer <token>`，**公网部署必开**，否则谁扫到端口谁白嫖 |
| `MAX_TRIES` | `10` | 单次请求最多换几个 key 重试 |
| `UPSTREAM` | `https://api.browser-use.com` | 上游地址 |

## 公网部署提示

```bash
PROXY_TOKEN=你自定义的密码 PORT=8787 nohup python proxy.py &
```

之后客户端要带两个头：`Authorization: Bearer 你自定义的密码` + `X-Browser-Use-API-Key: 随便填`。

## 注意

- keys.txt 别提交到 git，别公开分享本代理地址（不配 PROXY_TOKEN 等于把 200 个 key 送出去）
- key 是大佬发的，失效/封号是正常现象，代理会自动跳过坏 key；全部冷却时返回 4xx，等冷却结束或补充新 key 即可
