"""Queue-based integration with OpenClaw.

This module provides a file-based queue that OpenClaw can read
without any code changes to OpenClaw itself.

The service:
1. Polls Telegram for updates (or can use webhooks)
2. Downloads media to workspace/uploads/
3. Writes processed messages to a queue file
4. OpenClaw's existing session-memory reads from this queue
"""

import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Optional
from dataclasses import dataclass, asdict
from telegram_media_hook.config import get_config
from telegram_media_hook.hook import TelegramMediaHook

logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    """A message in the queue for OpenClaw to process."""
    id: str
    timestamp: str
    chat_id: int
    user_id: int
    original_text: str
    rewritten_text: str
    media_path: str  # workspace relative path
    media_type: str
    processed: bool = False


class MessageQueue:
    """File-based message queue for OpenClaw integration."""

    def __init__(self, queue_path: Optional[Path] = None):
        """Initialize the queue.

        Args:
            queue_path: Path to the queue file. Uses config if not provided.
        """
        self.config = get_config()
        self.queue_path = queue_path or self.config.queue_path

    def _ensure_queue_file(self) -> None:
        """Ensure the queue file exists."""
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.queue_path.exists():
            self._write_queue([])

    def _read_queue(self) -> list[dict]:
        """Read the queue from file."""
        self._ensure_queue_file()
        try:
            with open(self.queue_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_queue(self, queue: list[dict]) -> None:
        """Write the queue to file."""
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.queue_path, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)

    def add_message(self, message: QueuedMessage) -> None:
        """Add a message to the queue."""
        queue = self._read_queue()
        queue.append(asdict(message))
        self._write_queue(queue)
        logger.info(f"Added message to queue: {message.id}")

    def mark_processed(self, message_id: str) -> None:
        """Mark a message as processed."""
        queue = self._read_queue()
        for msg in queue:
            if msg["id"] == message_id:
                msg["processed"] = True
                break
        self._write_queue(queue)

    def get_pending_messages(self) -> list[QueuedMessage]:
        """Get all pending (unprocessed) messages."""
        queue = self._read_queue()
        return [
            QueuedMessage(**msg)
            for msg in queue
            if not msg.get("processed", False)
        ]

    def cleanup_processed(self, max_age_hours: int = 24) -> int:
        """Remove old processed messages from queue."""
        import time
        queue = self._read_queue()
        cutoff = time.time() - (max_age_hours * 3600)

        original_count = len(queue)
        queue = [
            msg for msg in queue
            if not msg.get("processed", False) or
            datetime.fromisoformat(msg["timestamp"]).timestamp() > cutoff
        ]

        deleted = original_count - len(queue)
        if deleted > 0:
            self._write_queue(queue)

        return deleted


class PollingService:
    """Telegram polling service that feeds the message queue."""

    def __init__(self):
        self.config = get_config()
        self.hook = TelegramMediaHook()
        self.queue = MessageQueue()
        self.offset = 0
        self.running = False

    async def start(self) -> None:
        """Start the polling service."""
        self.running = True
        logger.info("Starting Telegram polling service...")

        # Ensure upload directory exists
        self.config.upload_path.mkdir(parents=True, exist_ok=True)

        while self.running:
            try:
                await self._poll()
            except Exception as e:
                logger.error(f"Poll error: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    async def stop(self) -> None:
        """Stop the polling service."""
        self.running = False
        logger.info("Stopping Telegram polling service...")

    async def _poll(self) -> None:
        """Poll for new updates."""
        client = self.hook.telegram_client

        # Use getUpdates API
        async with client._get_client() as http:
            response = await http.get(
                f"{client.base_url}/getUpdates",
                params={
                    "offset": self.offset,
                    "timeout": 30,
                }
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                logger.error(f"API error: {data}")
                return

            for update in data.get("result", []):
                await self._handle_update(update)
                self.offset = update.get("update_id", 0) + 1

        # If no updates, wait before next poll
        await asyncio.sleep(self.config.poll_interval)

    async def _handle_update(self, update: dict) -> None:
        """Handle a single update."""
        message = update.get("message")
        if not message:
            return

        # Check for media
        has_media = "photo" in message or "document" in message
        if not has_media:
            return

        # Process the update
        result = await self.hook.handle_update(update)
        if not result or not result.media_info:
            return

        # Create queued message
        from telegram_media_hook.hook import MediaInfo

        media_info = result.media_info

        # Get user info
        user = message.get("from", {})
        chat = message.get("chat", {})

        queued = QueuedMessage(
            id=f"{update.get('update_id')}_{media_info.file_id[:8]}",
            timestamp=datetime.now().isoformat(),
            chat_id=chat.get("id", 0),
            user_id=user.get("id", 0),
            original_text=result.original_message,
            rewritten_text=result.rewritten_message or "",
            media_path=media_info.workspace_path,
            media_type=media_info.file_type,
        )

        self.queue.add_message(queued)
        logger.info(f"Processed media: {queued.media_path}")


async def run_service() -> None:
    """Run the polling service."""
    import signal
    import sys

    service = PollingService()

    # Handle shutdown signals
    def signal_handler(sig, frame):
        print("\nShutting down...")
        asyncio.create_task(service.stop())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    await service.start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    asyncio.run(run_service())
