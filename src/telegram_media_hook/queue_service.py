"""File-based message queue for tracking processed media.

Stores a record of fetched Telegram media so that:
- Items are not re-downloaded on subsequent fetch_telegram_media calls
- OpenClaw can track which media has been processed by a skill
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from telegram_media_hook.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    """A media item in the queue."""
    id: str
    timestamp: str
    chat_id: int
    user_id: int
    original_text: str
    rewritten_text: str
    media_path: str  # workspace-relative path
    media_type: str
    processed: bool = False


class MessageQueue:
    """File-based queue for tracking fetched Telegram media."""

    def __init__(self, queue_path: Optional[Path] = None):
        self.config = get_config()
        self.queue_path = queue_path or self.config.queue_path

    def _ensure_queue_file(self) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.queue_path.exists():
            self._write_queue([])

    def _read_queue(self) -> list[dict]:
        self._ensure_queue_file()
        try:
            with open(self.queue_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_queue(self, queue: list[dict]) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.queue_path, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False, indent=2)

    def add_message(self, message: QueuedMessage) -> None:
        """Add a media item to the queue."""
        queue = self._read_queue()
        queue.append(asdict(message))
        self._write_queue(queue)
        logger.info(f"Queued media: {message.id}")

    def mark_processed(self, message_id: str) -> None:
        """Mark a media item as processed."""
        queue = self._read_queue()
        for msg in queue:
            if msg["id"] == message_id:
                msg["processed"] = True
                break
        self._write_queue(queue)

    def get_pending_messages(self) -> list[QueuedMessage]:
        """Return all unprocessed media items."""
        queue = self._read_queue()
        return [
            QueuedMessage(**msg)
            for msg in queue
            if not msg.get("processed", False)
        ]

    def cleanup_processed(self, max_age_hours: int = 24) -> int:
        """Remove old processed items from the queue."""
        import time
        queue = self._read_queue()
        cutoff = time.time() - (max_age_hours * 3600)

        original_count = len(queue)
        queue = [
            msg for msg in queue
            if not msg.get("processed", False)
            or datetime.fromisoformat(msg["timestamp"]).timestamp() > cutoff
        ]

        deleted = original_count - len(queue)
        if deleted > 0:
            self._write_queue(queue)

        return deleted
