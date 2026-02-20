"""Async queue-based webhook server for Telegram Media Hook."""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from aiohttp import web
import aiofiles

from telegram_media_hook.config import get_config
from telegram_media_hook.hook import TelegramMediaHook

logger = logging.getLogger(__name__)


@dataclass
class QueuedUpdate:
    """An update in the queue."""
    id: str
    update: dict
    timestamp: str
    status: str = "pending"  # pending, processing, completed, failed
    result: Optional[dict] = None
    error: Optional[str] = None


class AsyncQueue:
    """Async message queue backed by JSON file."""

    def __init__(self, queue_path: Path):
        self.queue_path = queue_path
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)

    async def push(self, update: dict) -> str:
        """Push an update to the queue."""
        from datetime import datetime
        
        queued = QueuedUpdate(
            id=str(uuid.uuid4()),
            update=update,
            timestamp=datetime.now().isoformat(),
        )

        queue = await self._read_queue()
        queue.append(asdict(queued))
        await self._write_queue(queue)

        logger.info(f"Queued update: {queued.id}")
        return queued.id

    async def mark_status(
        self,
        update_id: str,
        status: str,
        result: Optional[dict] = None,
        error: Optional[str] = None
    ) -> None:
        """Mark an update's status."""
        queue = await self._read_queue()
        for item in queue:
            if item["id"] == update_id:
                item["status"] = status
                if result:
                    item["result"] = result
                if error:
                    item["error"] = error
                break
        await self._write_queue(queue)

    async def get_pending(self) -> list[dict]:
        """Get all pending updates."""
        queue = await self._read_queue()
        return [item for item in queue if item["status"] == "pending"]

    async def get_by_id(self, update_id: str) -> Optional[dict]:
        """Get an update by ID."""
        queue = await self._read_queue()
        for item in queue:
            if item["id"] == update_id:
                return item
        return None

    async def _read_queue(self) -> list:
        """Read queue from file."""
        if not self.queue_path.exists():
            return []
        try:
            async with aiofiles.open(self.queue_path, "r") as f:
                content = await f.read()
                return json.loads(content) if content else []
        except (json.JSONDecodeError, IOError):
            return []

    async def _write_queue(self, queue: list) -> None:
        """Write queue to file."""
        async with aiofiles.open(self.queue_path, "w") as f:
            await f.write(json.dumps(queue, ensure_ascii=False, indent=2))


class WebhookServer:
    """Telegram webhook server with async queue processing."""

    def __init__(self):
        self.config = get_config()
        self.hook = TelegramMediaHook()
        self.queue = AsyncQueue(self.config.workspace_root / "uploads" / "webhook_queue.json")
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        """Setup web routes."""
        self.app.router.add_post("/webhook", self.handle_webhook)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/queue", self.handle_queue_status)
        self.app.router.add_post("/queue/{update_id}/retry", self.handle_retry)

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming Telegram webhook."""
        try:
            update = await request.json()
            update_id = await self.queue.push(update)

            # Process asynchronously
            asyncio.create_task(self._process_update(update_id))

            # Immediately acknowledge to Telegram
            return web.json_response({"ok": True, "update_id": update_id})

        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return web.json_response({"ok": False, "error": str(e)}, status=500)

    async def _process_update(self, update_id: str) -> None:
        """Process a queued update."""
        from datetime import datetime
        
        try:
            await self.queue.mark_status(update_id, "processing")

            # Get the update
            update = await self.queue.get_by_id(update_id)
            if not update:
                return

            # Process the update with the hook
            result = await self.hook.handle_update(update["update"])

            if result and result.media_info:
                # Save result
                await self.queue.mark_status(
                    update_id,
                    "completed",
                    result={
                        "media_path": result.media_info.workspace_path,
                        "message": result.rewritten_message,
                    }
                )

                # Send notification back to Telegram
                await self._send_telegram_notification(
                    update["update"],
                    result.rewritten_message,
                    result.media_info.workspace_path
                )
            else:
                await self.queue.mark_status(update_id, "completed")

        except Exception as e:
            logger.error(f"Processing error for {update_id}: {e}")
            await self.queue.mark_status(update_id, "failed", error=str(e))

    async def _send_telegram_notification(
        self,
        update: dict,
        message: str,
        media_path: str
    ) -> None:
        """Send a notification back to Telegram user."""
        message_data = update.get("message", {})
        chat = message_data.get("chat", {})
        chat_id = chat.get("id")

        if not chat_id:
            return

        # Send confirmation message
        notification_text = (
            f"✅ 图片已保存！\n\n"
            f"路径: `{media_path}`\n\n"
            f"正在生成解答..."
        )

        client = self.hook.telegram_client
        async with client._get_client() as http:
            await http.post(
                f"{client.base_url}/sendMessage",
                params={
                    "chat_id": chat_id,
                    "text": notification_text,
                    "parse_mode": "Markdown",
                }
            )

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "ok"})

    async def handle_queue_status(self, request: web.Request) -> web.Response:
        """Get queue status."""
        pending = await self.queue.get_pending()
        return web.json_response({
            "pending": len(pending),
            "items": pending[:10],  # Return first 10
        })

    async def handle_retry(self, request: web.Request) -> web.Response:
        """Retry a failed update."""
        update_id = request.match_info["update_id"]
        
        update = await self.queue.get_by_id(update_id)
        if not update:
            return web.json_response({"error": "Not found"}, status=404)

        await self.queue.mark_status(update_id, "pending")
        asyncio.create_task(self._process_update(update_id))

        return web.json_response({"ok": True})

    async def start(self, host: str = "0.0.0.0", port: int = 8080):
        """Start the webhook server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info(f"Webhook server started on http://{host}:{port}")
        return runner


async def run_server():
    """Run the webhook server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    server = WebhookServer()
    await server.start(port=8080)
    
    # Keep running
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(run_server())
