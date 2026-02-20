"""HTTP API for queue management.

Gateway calls this API to add file_ids to the queue when it receives media.
"""

from datetime import datetime

from aiohttp import web

from telegram_media_hook.queue_service import locked_queue, read_queue


async def handle_add(request: web.Request) -> web.Response:
    """Add a file_id to the pending queue."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    file_id = data.get("file_id")
    if not file_id:
        return web.json_response({"error": "file_id required"}, status=400)

    with locked_queue() as queue:
        for item in queue.get("pending", []):
            if item.get("file_id") == file_id:
                return web.json_response({"ok": True, "message": "Already in queue"})
        queue.setdefault("pending", []).append({
            "file_id": file_id,
            "message_id": data.get("message_id", 0),
            "chat_id": data.get("chat_id", 0),
            "caption": data.get("caption", ""),
            "queued_at": datetime.now().isoformat(),
            "retry_count": 0,
        })

    return web.json_response({"ok": True, "file_id": file_id})


async def handle_status(request: web.Request) -> web.Response:
    """Return a summary of the current queue state."""
    queue = read_queue()
    return web.json_response({
        "pending": queue.get("pending", []),
        "processed_count": len(queue.get("processed", [])),
        "failed": queue.get("failed", []),
    })


async def handle_health(request: web.Request) -> web.Response:
    """Health check."""
    return web.json_response({"status": "ok"})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/add", handle_add)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/health", handle_health)
    return app


def run_server(port: int = 8081) -> None:
    """Run the queue API server."""
    app = create_app()
    web.run_app(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    run_server()
