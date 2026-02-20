"""Simple HTTP API for queue management.

Gateway can call this API to add file_ids to the queue when receiving media.
"""

import asyncio
import json
from aiohttp import web
from pathlib import Path
from datetime import datetime

from telegram_media_hook.config import get_config


def _get_queue_path() -> Path:
    config = get_config()
    return config.workspace_root / "uploads" / "telegram_media_queue.json"


def _ensure_queue() -> dict:
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
    queue_path = _get_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


async def handle_add(request: web.Request) -> web.Response:
    """Add file_id to queue."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    file_id = data.get("file_id")
    if not file_id:
        return web.json_response({"error": "file_id required"}, status=400)
    
    queue = _ensure_queue()
    
    # Check if already in queue
    for item in queue.get("pending", []):
        if item.get("file_id") == file_id:
            return web.json_response({"ok": True, "message": "Already in queue"})
    
    queue.setdefault("pending", []).append({
        "file_id": file_id,
        "message_id": data.get("message_id", 0),
        "chat_id": data.get("chat_id", 0),
        "caption": data.get("caption", ""),
        "queued_at": datetime.now().isoformat(),
    })
    
    _save_queue(queue)
    
    return web.json_response({"ok": True, "file_id": file_id})


async def handle_status(request: web.Request) -> web.Response:
    """Get queue status."""
    queue = _ensure_queue()
    return web.json_response(queue)


async def handle_health(request: web.Request) -> web.Response:
    """Health check."""
    return web.json_response({"status": "ok"})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/add", handle_add)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/health", handle_health)
    return app


def run_server(port: int = 8081):
    """Run the queue API server."""
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run_server()
