"""MCP server for Telegram media hook.

Gateway → MCP collaboration:
1. Gateway receives media and writes file_id to the queue.
2. MCP reads the queue, downloads files, and saves them to the workspace.
3. Gateway needs no changes — the queue path is configured via env.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from telegram_media_hook.config import get_config
from telegram_media_hook.queue_service import MAX_RETRIES, locked_queue, read_queue

logger = logging.getLogger(__name__)


def _get_offset_path() -> Path:
    return get_config().queue_path.with_name("telegram_poll_offset.json")


def _read_offset() -> int:
    path = _get_offset_path()
    if not path.exists():
        return 0
    try:
        with open(path) as f:
            return json.load(f).get("offset", 0)
    except (json.JSONDecodeError, IOError):
        return 0


def _write_offset(offset: int) -> None:
    path = _get_offset_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"offset": offset}, f)


mcp = FastMCP(
    "telegram-media-hook",
    instructions=(
        "Fetch media uploaded via Telegram bot and save to OpenClaw workspace. "
        "Gateway writes file_ids to the queue; MCP downloads them."
    ),
)


@mcp.tool()
async def fetch_telegram_media() -> dict[str, Any]:
    """Poll queue for new media uploads and download them to workspace.

    Gateway writes file_ids to the queue when it receives media.
    This tool reads those entries and downloads the actual files.
    """
    from telegram_media_hook.file_manager import FileManager
    from telegram_media_hook.telegram_client import TelegramClient

    config = get_config()
    config.upload_path.mkdir(parents=True, exist_ok=True)

    # Claim all pending items atomically, then release the lock before
    # performing slow network I/O so other writers are not blocked.
    with locked_queue() as queue:
        to_process = list(queue.get("pending", []))
        queue["pending"] = []  # Optimistically clear — failures are re-queued below.

    if not to_process:
        return {
            "fetched": [],
            "count": 0,
            "message": "No pending media in queue. Make sure Gateway is running.",
        }

    client = TelegramClient()
    file_manager = FileManager()
    fetched: list[dict] = []
    still_pending: list[dict] = []
    newly_failed: list[dict] = []

    for item in to_process:
        file_id = item.get("file_id")
        if not file_id:
            continue

        try:
            file_info, content = await client.get_file_info(file_id)

            # Infer extension from Telegram's file_path (e.g. "photos/file_123.jpg")
            # so documents, videos, etc. keep the correct extension.
            original_name = (
                Path(file_info.file_path).name if file_info.file_path else "photo.jpg"
            )
            filename = file_manager.generate_filename(original_name)
            file_path = await file_manager.save_file(content, filename)
            workspace_path = file_manager.get_workspace_relative_path(file_path)

            fetched.append({
                "id": item.get("message_id", file_id[:8]),
                "file_id": file_id,
                "path": str(file_path),
                "workspace_path": workspace_path,
                "caption": item.get("caption", ""),
            })

        except Exception as e:
            logger.error(f"Failed to download {file_id}: {e}")
            retry_count = item.get("retry_count", 0) + 1
            if retry_count >= MAX_RETRIES:
                logger.warning(f"Giving up on {file_id} after {retry_count} attempts")
                newly_failed.append({**item, "error": str(e), "retry_count": retry_count})
            else:
                still_pending.append({**item, "retry_count": retry_count})

    # Write results back, prepending re-queued failures so they are retried
    # first, and merging with any items added while we were downloading.
    with locked_queue() as queue:
        queue["pending"] = still_pending + queue.get("pending", [])
        for result in fetched:
            orig = next((p for p in to_process if p.get("file_id") == result["file_id"]), {})
            queue.setdefault("processed", []).append({
                **orig,
                "downloaded_at": datetime.now().isoformat(),
                "workspace_path": result["workspace_path"],
            })
        queue.setdefault("failed", []).extend(newly_failed)

    return {
        "fetched": fetched,
        "count": len(fetched),
        "message": f"Downloaded {len(fetched)} media file(s)" if fetched else "No files downloaded",
    }


@mcp.tool()
async def list_pending_media() -> dict[str, Any]:
    """List media items waiting in the queue."""
    queue = read_queue()
    return {
        "pending": queue.get("pending", []),
        "count": len(queue.get("pending", [])),
        "failed": queue.get("failed", []),
    }


@mcp.tool()
async def mark_media_processed(file_id: str) -> dict[str, Any]:
    """Remove a media item from the pending queue by file_id."""
    with locked_queue() as queue:
        before = len(queue.get("pending", []))
        queue["pending"] = [p for p in queue.get("pending", []) if p.get("file_id") != file_id]
        removed = before - len(queue["pending"])
    return {"ok": True, "file_id": file_id, "removed": removed}


@mcp.tool()
async def add_to_queue(
    file_id: str,
    message_id: int = 0,
    chat_id: int = 0,
    caption: str = "",
) -> dict[str, Any]:
    """Manually add a file_id to the queue (for testing or Gateway integration).

    Args:
        file_id: Telegram file_id of the media.
        message_id: Optional message ID.
        chat_id: Optional chat ID.
        caption: Optional caption/text accompanying the media.
    """
    with locked_queue() as queue:
        for item in queue.get("pending", []):
            if item.get("file_id") == file_id:
                return {"ok": False, "error": "Already in queue", "file_id": file_id}
        queue.setdefault("pending", []).append({
            "file_id": file_id,
            "message_id": message_id,
            "chat_id": chat_id,
            "caption": caption,
            "queued_at": datetime.now().isoformat(),
            "retry_count": 0,
        })
    return {"ok": True, "file_id": file_id, "message": "Added to queue"}


@mcp.tool()
async def poll_telegram(timeout: int = 5) -> dict[str, Any]:
    """Fetch new Telegram messages and download any media to workspace.

    Uses getUpdates long-polling — no webhook or public URL required.
    Safe to call from behind NAT (Raspberry Pi, home network, etc.).

    Args:
        timeout: Seconds to wait for new messages (0–30). Use 0 for an
                 immediate check, 5–10 to wait a bit for a pending upload.
    """
    from telegram_media_hook.file_manager import FileManager
    from telegram_media_hook.telegram_client import TelegramClient

    config = get_config()
    config.upload_path.mkdir(parents=True, exist_ok=True)

    client = TelegramClient()
    file_manager = FileManager()

    offset = _read_offset()
    updates = await client.get_updates(offset=offset, timeout=timeout)

    fetched: list[dict] = []
    new_offset = offset

    for update in updates:
        update_id = update.get("update_id", 0)
        new_offset = max(new_offset, update_id + 1)

        message = update.get("message") or update.get("edited_message")
        if not message:
            continue

        file_id = None
        file_type = None
        caption = message.get("caption", "")

        if "photo" in message:
            file_id = message["photo"][-1].get("file_id")  # largest size
            file_type = "photo"
        elif "document" in message:
            file_id = message["document"].get("file_id")
            file_type = "document"
        elif "video" in message:
            file_id = message["video"].get("file_id")
            file_type = "video"

        if not file_id:
            continue

        try:
            file_info, content = await client.get_file_info(file_id)
            original_name = (
                Path(file_info.file_path).name if file_info.file_path else "media"
            )
            filename = file_manager.generate_filename(original_name)
            file_path = await file_manager.save_file(content, filename)
            workspace_path = file_manager.get_workspace_relative_path(file_path)

            fetched.append({
                "update_id": update_id,
                "message_id": message.get("message_id"),
                "chat_id": message.get("chat", {}).get("id"),
                "file_id": file_id,
                "type": file_type,
                "path": str(file_path),
                "workspace_path": workspace_path,
                "caption": caption,
            })
        except Exception as e:
            logger.error(f"Failed to download {file_id}: {e}")

    _write_offset(new_offset)

    return {
        "fetched": fetched,
        "count": len(fetched),
        "message": (
            f"Downloaded {len(fetched)} media file(s)"
            if fetched
            else "No new media messages"
        ),
    }


@mcp.tool()
async def delete_webhook() -> dict[str, Any]:
    """Remove any configured Telegram webhook so getUpdates polling can work.

    Call this once if poll_telegram returns a conflict error.
    """
    import httpx
    config = get_config()
    async with httpx.AsyncClient(timeout=10.0, proxy=None) as client:
        response = await client.get(
            f"https://api.telegram.org/bot{config.bot_token}/deleteWebhook"
        )
        data = response.json()
    return {"ok": data.get("ok"), "description": data.get("description", "")}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
