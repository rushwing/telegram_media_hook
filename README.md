# telegram-media-hook

MCP server that bridges Telegram media uploads to an OpenClaw workspace.

When you send a photo or video to your Telegram bot, OpenClaw can call
`fetch_telegram_media` to download it on demand — no webhook, no public URL,
no background service.

## How It Works

```
You upload photo → Telegram bot
                        │
             (buffered until fetched)
                        │
OpenClaw skill calls fetch_telegram_media()
                        │
          MCP server polls Telegram once
          downloads file → workspace/uploads/
          returns local file path
                        │
        Skill uses path to generate solution
```

The MCP server runs as a child process of OpenClaw (stdio transport).
It starts when OpenClaw starts, sleeps at ~0% CPU when idle, and only
hits the Telegram API when a skill explicitly calls a tool.

## Prerequisites

- Telegram bot token from [@BotFather](https://t.me/BotFather)
- OpenClaw running on Raspberry Pi 5 with `uv` installed
- `uv` installed on your Mac for building

## Quick Start

### 1. Configure

```bash
cp .env.example .env
# edit .env — set TELEGRAM_BOT_TOKEN and OPENCLAW_WORKSPACE
```

### 2. Build

```bash
./scripts/build.sh
# produces dist/telegram_media_hook-*.whl
```

### 3. Deploy to Pi

```bash
PI_HOST=openclaw@raspberrypi.local \
TELEGRAM_BOT_TOKEN=your-token \
OPENCLAW_WORKSPACE=/home/openclaw/.openclaw/workspace \
./scripts/deploy.sh
```

The deploy script:
1. Copies the wheel to the Pi via `scp`
2. Installs it with `uv tool install` (isolated env, available as a command)
3. Patches `~/.openclaw/openclaw.json` to register the MCP server

### 4. Restart OpenClaw

OpenClaw reads `mcpServers` at startup. Restart it on the Pi to pick up
the new server.

## MCP Tools

| Tool | Description |
|------|-------------|
| `fetch_telegram_media()` | Poll Telegram once, download any new media, return file paths |
| `list_pending_media()` | List fetched media not yet marked as processed |
| `mark_media_processed(media_id)` | Mark a media item as done |

### `fetch_telegram_media` response

```json
{
  "count": 1,
  "message": "Downloaded 1 media file(s)",
  "fetched": [
    {
      "id": "789012345_a1b2c3d4",
      "path": "/home/openclaw/.openclaw/workspace/uploads/20260221_143256_a1b2c3d4.jpg",
      "workspace_path": "uploads/20260221_143256_a1b2c3d4.jpg",
      "type": "photo",
      "caption": "solve this"
    }
  ]
}
```

## openclaw.json

The deploy script adds this automatically. For manual setup:

```json
{
  "mcpServers": {
    "telegram-media": {
      "command": "telegram-media-hook-mcp",
      "env": {
        "TELEGRAM_BOT_TOKEN": "your-token",
        "OPENCLAW_WORKSPACE": "/home/openclaw/.openclaw/workspace"
      }
    }
  }
}
```

## Skill Integration

In your tutor/solver skill, call the MCP tool when the user says they've
uploaded something:

```
User: "I sent a photo of the problem, solve it"

→ Call fetch_telegram_media()
← {count: 1, fetched: [{path: "/home/pi/.../uploads/20260221_..._abc.jpg", type: "photo"}]}

→ Read image at path
→ Run vision model / solution generator
→ Call mark_media_processed("789012345_a1b2c3d4")
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | — | Required. Bot token from @BotFather |
| `OPENCLAW_WORKSPACE` | `/home/openclaw/.openclaw/workspace` | Workspace root on the Pi |
| `UPLOAD_DIR` | `uploads` | Media save directory (relative to workspace) |
| `MAX_FILE_SIZE_MB` | `20` | Telegram file size limit |
| `QUEUE_FILE` | `uploads/message_queue.json` | Queue tracking file (relative to workspace) |

## Project Structure

```
telegram_media_hook/
├── src/telegram_media_hook/
│   ├── mcp_server.py       # MCP server — tools exposed to OpenClaw
│   ├── hook.py             # Core logic — download and save media
│   ├── telegram_client.py  # Telegram Bot API client
│   ├── file_manager.py     # File storage in workspace
│   ├── queue_service.py    # Queue for tracking processed media
│   ├── config.py           # Configuration from env vars
│   └── __main__.py         # CLI (test, cleanup, serve)
├── scripts/
│   ├── build.sh            # Build wheel on Mac
│   └── deploy.sh           # Deploy to Raspberry Pi
├── .env.example
└── pyproject.toml
```

## CLI Commands

```bash
# Test configuration
telegram-media-hook test

# Run MCP server manually (normally started by OpenClaw)
telegram-media-hook serve

# Clean up old uploaded files and queue entries
telegram-media-hook cleanup --max-age 30

# Process a saved update JSON file (for debugging)
telegram-media-hook process update.json
```
