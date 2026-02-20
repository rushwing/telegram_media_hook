"""MCP server for Telegram media hook.

Exposes three tools to OpenClaw:
  - fetch_telegram_media   poll Telegram once and download any new media
  - list_pending_media     list fetched-but-unprocessed items in the queue
  - mark_media_processed   mark a queue item as done

Configure in openclaw.json:
    {
      "mcpServers": {
        "telegram-media": {
          "command": "telegram-media-hook-mcp",
          "env": {
            "TELEGRAM_BOT_TOKEN": "your-token",
            "OPENCLAW_WORKSPACE": "/path/to/workspace"
          }
        }
      }
    }
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from telegram_media_hook.config import get_config
from telegram_media_hook.hook import TelegramMediaHook
from telegram_media_hook.queue_service import MessageQueue, QueuedMessage

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "telegram-media-hook",
    instructions="Fetch media uploaded via Telegram bot and save to OpenClaw workspace",
)


def _offset_path() -> Path:
    return get_config().upload_path / ".telegram_offset"


def _read_offset() -> int:
    path = _offset_path()
    if path.exists():
        try:
            return int(path.read_text().strip())
        except (ValueError, OSError):
            pass
    return 0


def _write_offset(offset: int) -> None:
    path = _offset_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(offset))


@mcp.tool()
async def fetch_telegram_media() -> dict[str, Any]:
    """Poll Telegram once for new media uploads and save them to the workspace.

    Call this when the user says they have uploaded a photo or video to the
    Telegram bot. Returns the local file paths so you can use them immediately.
    """
    config = get_config()
    hook = TelegramMediaHook()
    queue = MessageQueue()
    client = hook.telegram_client

    config.upload_path.mkdir(parents=True, exist_ok=True)
    offset = _read_offset()
    fetched = []

    async with client._get_client() as http:
        response = await http.get(
            f"{client.base_url}/getUpdates",
            params={"offset": offset, "timeout": 0},
        )
        response.raise_for_status()
        data = response.json()

    if not data.get("ok"):
        return {"error": data.get("description", "Telegram API error"), "fetched": [], "count": 0}

    for update in data.get("result", []):
        new_offset = update.get("update_id", 0) + 1
        if new_offset > offset:
            offset = new_offset

        result = await hook.handle_update(update)
        if not result or not result.media_info:
            continue

        message = update.get("message", {})
        queued = QueuedMessage(
            id=f"{update.get('update_id')}_{result.media_info.file_id[:8]}",
            timestamp=datetime.now().isoformat(),
            chat_id=message.get("chat", {}).get("id", 0),
            user_id=message.get("from", {}).get("id", 0),
            original_text=result.original_message,
            rewritten_text=result.rewritten_message or "",
            media_path=result.media_info.workspace_path,
            media_type=result.media_info.file_type,
        )
        queue.add_message(queued)

        fetched.append({
            "id": queued.id,
            "path": result.media_info.file_path,
            "workspace_path": result.media_info.workspace_path,
            "type": result.media_info.file_type,
            "caption": result.original_message,
        })

    _write_offset(offset)

    return {
        "fetched": fetched,
        "count": len(fetched),
        "message": f"Downloaded {len(fetched)} media file(s)" if fetched else "No new media found",
    }


@mcp.tool()
async def list_pending_media() -> dict[str, Any]:
    """List media files that have been fetched but not yet marked as processed.

    Useful for checking what is waiting if fetch_telegram_media was called
    in a previous session.
    """
    queue = MessageQueue()
    pending = queue.get_pending_messages()
    return {
        "pending": [
            {
                "id": m.id,
                "path": m.media_path,
                "type": m.media_type,
                "caption": m.original_text,
                "timestamp": m.timestamp,
            }
            for m in pending
        ],
        "count": len(pending),
    }


@mcp.tool()
async def mark_media_processed(media_id: str) -> dict[str, Any]:
    """Mark a media item as processed after the skill has handled it.

    Args:
        media_id: The id field returned by fetch_telegram_media or list_pending_media.
    """
    queue = MessageQueue()
    queue.mark_processed(media_id)
    return {"ok": True, "media_id": media_id}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
