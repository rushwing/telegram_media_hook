# Telegram Media Hook

> Telegram → OpenClaw workspace bridge with Webhook + Async Queue

## Architecture

```
Telegram Bot API
       │
       ▼ (webhook)
┌──────────────────┐
│  Webhook Server  │ ◄── Async processing
│  (aiohttp)       │
└────────┬─────────┘
         │
         ▼ (queue)
┌──────────────────┐
│   JSON Queue     │ ◄── Persistent queue
└────────┬─────────┘
         │
         ▼ (process)
┌──────────────────┐
│  Download Media  │ ◄── Save to workspace/uploads/
└────────┬─────────┘
         │
         ▼ (notify)
┌──────────────────┐
│  Telegram User  │ ◄── Send confirmation message
└──────────────────┘
```

## Quick Start

### 1. 安装

```bash
cd telegram_media_hook
uv sync
```

### 2. 配置

```bash
# 复制 .env.example 到 .env
cp .env.example .env

# 编辑配置
nano .env
```

### 3. 启动 Webhook 服务器

```bash
# 启动服务（需要公网访问）
PYTHONPATH=src python -m telegram_media_hook webhook --port 8080
```

### 4. 设置 Telegram Webhook

```bash
# 方式 1: 使用 ngrok（开发用）
ngrok http 8080

# 方式 2: 购买域名（生产用）

# 设置 webhook
curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \
  -d url=https://your-public-url/webhook
```

## 使用方法

### 命令

| 命令 | 说明 |
|------|------|
| `webhook` | 启动 webhook 服务器 |
| `setup-webhook <url>` | 打印设置 webhook 的 curl 命令 |
| `queue-status` | 查看队列状态 |
| `test` | 测试配置 |
| `cleanup` | 清理旧文件 |

### API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/webhook` | POST | Telegram 回调 |
| `/health` | GET | 健康检查 |
| `/queue` | GET | 队列状态 |
| `/queue/{id}/retry` | POST | 重试失败任务 |

## Telegram 通知

当图片上传并处理完成后，用户会收到通知：

```
✅ 图片已保存！

路径: `uploads/20260220_143256_abc123.jpg`

正在生成解答...
```

## OpenClaw 集成

图片保存后，Skill 可以直接读取：

```python
# 在你的 SKILL.md 或 skill 代码中
image_path = "/home/openclaw/.openclaw/workspace/uploads/20260220_143256_abc123.jpg"
with open(image_path, "rb") as f:
    image_data = f.read()
```

## 环境变量

```bash
TELEGRAM_BOT_TOKEN=your-bot-token
OPENCLAW_WORKSPACE=/home/openclaw/.openclaw/workspace
UPLOAD_DIR=uploads
MAX_FILE_SIZE_MB=20
WEBHOOK_PORT=8080
PUBLIC_WEBHOOK_URL=https://your-public-url
QUEUE_FILE=uploads/webhook_queue.json
```

## 项目结构

```
telegram_media_hook/
├── src/telegram_media_hook/
│   ├── __init__.py
│   ├── __main__.py           # CLI
│   ├── config.py             # 配置
│   ├── hook.py               # 核心 Hook
│   ├── telegram_client.py    # Telegram API
│   ├── file_manager.py       # 文件存储
│   ├── queue_service.py      # 轮询服务（旧）
│   └── webhook_server.py     # Webhook 服务器（新）
├── scripts/
│   ├── bridge.sh
│   └── ...
├── .env.example
├── pyproject.toml
└── README.md
```

## 生产部署建议

1. **使用 PM2 或 Systemd** 运行 webhook 服务器
2. **配置 SSL**（Telegram 要求 HTTPS）
3. **使用 Redis** 替代 JSON 文件队列（可选）
4. **配置日志轮转**

### Systemd 示例

```ini
[Unit]
Description=Telegram Media Hook
After=network.target

[Service]
Type=simple
User=openclaw
WorkingDirectory=/home/openclaw/.openclaw/workspace/telegram_media_hook
Environment=PYTHONPATH=src
ExecStart=/home/openclaw/.openclaw/workspace/telegram_media_hook/.venv/bin/python -m telegram_media_hook webhook --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
```
