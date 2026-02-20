"""MCP server for Telegram media hook.

Gateway → MCP 协作模式：
1. Gateway 收到图片时，写入 file_id 到队列
2. MCP 从队列读取并下载图片
3. Gateway 不需要改动（通过配置文件指定队列路径）

队列格式 (telegram_media_queue.json):
{
  "pending": [
    {"file_id": "xxx", "message_id": 123, "chat_id": 456, "timestamp": "..."}
  ],
  "processed": [...]
}
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from telegram_media_hook.config import get_config

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "telegram-media-hook",
    instructions="Fetch media uploaded via Telegram bot and save to OpenClaw workspace. Gateway writes file_ids to queue, MCP downloads.",
)


def _get_queue_path() -> Path:
    """Get the queue file path."""
    config = get_config()
    return config.workspace_root / "uploads" / "telegram_media_queue.json"


def _ensure_queue() -> dict:
    """Ensure queue file exists."""
    queue_path = _get_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not queue_path.exists():
        return {"pending": [], "processed": []}
    
    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"pending": [], "processed": []}


def _save_queue(queue: dict) -> None:
    """Save queue to file."""
    queue_path = _get_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


@mcp.tool()
async def fetch_telegram_media() -> dict[str, Any]:
    """Poll queue for new media uploads and download them to workspace.
    
    Gateway should write file_ids to the queue when receiving media.
    This tool reads the queue and downloads the files.
    """
    config = get_config()
    config.upload_path.mkdir(parents=True, exist_ok=True)
    
    queue = _ensure_queue()
    pending = queue.get("pending", [])
    fetched = []
    
    if not pending:
        return {
            "fetched": [],
            "count": 0,
            "message": "No pending media in queue. Make sure Gateway is running.",
        }
    
    # Process each pending item
    for item in pending:
        file_id = item.get("file_id")
        if not file_id:
            continue
        
        try:
            # Download the file
            from telegram_media_hook.telegram_client import TelegramClient
            client = TelegramClient()
            
            file_info, content = await client.get_file_info(file_id)
            
            # Generate filename
            from telegram_media_hook.file_manager import FileManager
            file_manager = FileManager()
            filename = file_manager.generate_filename("photo.jpg")
            file_path = await file_manager.save_file(content, filename)
            workspace_path = file_manager.get_workspace_relative_path(file_path)
            
            fetched.append({
                "id": item.get("message_id", file_id[:8]),
                "file_id": file_id,
                "path": str(file_path),
                "workspace_path": workspace_path,
                "type": "photo",
                "caption": item.get("caption", ""),
            })
            
            # Move to processed
            queue["processed"].append({
                **item,
                "downloaded_at": datetime.now().isoformat(),
                "workspace_path": workspace_path,
            })
            
        except Exception as e:
            logger.error(f"Failed to download {file_id}: {e}")
            # Keep in pending for retry
            continue
    
    # Remove processed items from pending
    processed_ids = {item["file_id"] for item in queue.get("processed", []) if "downloaded_at" in item}
    queue["pending"] = [p for p in pending if p.get("file_id") not in processed_ids]
    
    _save_queue(queue)
    
    return {
        "fetched": fetched,
        "count": len(fetched),
        "message": f"Downloaded {len(fetched)} media file(s)" if fetched else "No files downloaded",
    }


@mcp.tool()
async def list_pending_media() -> dict[str, Any]:
    """List media items waiting in the queue."""
    queue = _ensure_queue()
    pending = queue.get("pending", [])
    
    return {
        "pending": pending,
        "count": len(pending),
    }


@mcp.tool()
async def mark_media_processed(media_id: str) -> dict[str, Any]:
    """Mark a media item as processed (remove from queue)."""
    queue = _ensure_queue()
    
    # Find and remove from pending
    pending = queue.get("pending", [])
    queue["pending"] = [p for p in pending if str(p.get("message_id", "")) != media_id]
    
    _save_queue(queue)
    
    return {"ok": True, "media_id": media_id}


@mcp.tool()
async def add_to_queue(file_id: str, message_id: int = 0, chat_id: int = 0, caption: str = "") -> dict[str, Any]:
    """Manually add a file_id to the queue (for testing or Gateway integration).
    
    Args:
        file_id: Telegram file_id of the media
        message_id: Optional message ID
        chat_id: Optional chat ID
        caption: Optional caption/text with the media
    """
    queue = _ensure_queue()
    
    # Check if already in queue
    for item in queue.get("pending", []):
        if item.get("file_id") == file_id:
            return {"ok": False, "error": "Already in queue", "file_id": file_id}
    
    queue.setdefault("pending", []).append({
        "file_id": file_id,
        "message_id": message_id,
        "chat_id": chat_id,
        "caption": caption,
        "queued_at": datetime.now().isoformat(),
    })
    
    _save_queue(queue)
    
    return {"ok": True, "file_id": file_id, "message": "Added to queue"}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
