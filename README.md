# Browser Use Cloud API 反向代理（key 池版）

透明反代 `https://api.browser-use.com`，自动从 key 池轮换注入 `X-Browser-Use-API-Key`。
挂了（401/402/403）自动冷却 5 分钟，限流（429）冷却 1 分钟，自动换下一个重试。

**内置 OpenAI 兼容转接层**（`/v1/chat/completions`、`/v1/models`）：把聊天请求包装成 Browser Use 的 agent run，
让 opencode、ChatBox、Cherry Studio 等工具可以直接使用这批 key（就是别人做的那种"转接"）。

## 接到 opencode

`opencode.json` 加自定义 provider：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "browseruse": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "BrowserUse",
      "options": { "baseURL": "http://127.0.0.1:8787/v1", "apiKey": "sk-anything" },
      "models": { "grok-4.5": { "name": "BU grok-4.5" } }
    }
  }
}
```

其他聊天工具同理：API 类型选 **OpenAI 兼容**，Base URL 填 `http://127.0.0.1:8787/v1`，Key 随便填。
可用模型名（填错自动回退到 DEFAULT_MODEL）：`grok-4.5`、`gpt-5.5`、`claude-sonnet-5`、`kimi-k3`、`gemini-3.5-flash` 等，完整列表看 `GET /v1/models`。

**转接层注意事项（体验打折，先知道）**：
- 每条消息 = 一次完整云端 agent run，回复要**几十秒到几分钟**，不是秒回
- 消耗的是 agent 额度（云端要开浏览器虚拟机），比直接调 LLM 的 token 贵得多
- 不支持 function calling，opencode 的自动改文件/跑命令能力会退化，基本只能问答
- 适合轻量问答；重度编程还是建议用正经 LLM 的 key

## 免终端启动（推荐）

- **Windows**：双击 `start-windows.bat`
- **Mac**：双击 `start-mac.command`（首次若被系统拦：右键 → 打开）

启动器会自动检查 Python、装依赖、从 `keys.example.txt` 生成 `keys.txt`（不存在时）、发现没填真 key 时帮你打开编辑器，然后启动代理。
真 key 填进 `keys.txt`（它已被 .gitignore 排除，永远不会被提交）。
窗口最小化即可挂着跑，**关闭窗口 = 停止代理**。

## 手动启动（终端）

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
| `DEFAULT_MODEL` | `grok-4.5` | 转接层默认模型（客户端填了无效模型名时用它） |
| `CHAT_TIMEOUT` | `600` | 转接层单次对话最长等待秒数 |

## 公网部署提示

```bash
PROXY_TOKEN=你自定义的密码 PORT=8787 nohup python proxy.py &
```

之后客户端要带两个头：`Authorization: Bearer 你自定义的密码` + `X-Browser-Use-API-Key: 随便填`。

## 注意

- keys.txt 别提交到 git，别公开分享本代理地址（不配 PROXY_TOKEN 等于把 200 个 key 送出去）
- key 是大佬发的，失效/封号是正常现象，代理会自动跳过坏 key；全部冷却时返回 4xx，等冷却结束或补充新 key 即可
