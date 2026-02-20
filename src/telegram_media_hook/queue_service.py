"""Shared file-based queue for Gateway and MCP server.

Provides atomic read/write helpers with file locking so that
the Gateway (queue_api) and MCP server processes can safely share
the same JSON file without data races.

Queue format (telegram_media_queue.json):
{
  "pending":   [{"file_id": "...", "message_id": 0, "chat_id": 0,
                 "caption": "...", "queued_at": "...", "retry_count": 0}],
  "processed": [{"file_id": "...", ..., "downloaded_at": "...",
                 "workspace_path": "..."}],
  "failed":    [{"file_id": "...", ..., "error": "...", "retry_count": 3}]
}
"""

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from filelock import FileLock

from telegram_media_hook.config import get_config

MAX_RETRIES = 3


def get_queue_path() -> Path:
    """Return the path to the queue JSON file."""
    return get_config().queue_path


def _lock_path() -> Path:
    return get_queue_path().with_suffix(".lock")


def _read_raw() -> dict:
    queue_path = get_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    if not queue_path.exists():
        return {"pending": [], "processed": [], "failed": []}
    try:
        with open(queue_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("failed", [])
        return data
    except (json.JSONDecodeError, IOError):
        return {"pending": [], "processed": [], "failed": []}


def _write_raw(queue: dict) -> None:
    queue_path = get_queue_path()
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with open(queue_path, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


@contextmanager
def locked_queue() -> Generator[dict, None, None]:
    """Acquire a file lock, yield the mutable queue dict, then write it back.

    Use this for any read-modify-write operation to prevent data races
    between the Gateway (queue_api) and MCP server processes.

    Example::

        with locked_queue() as queue:
            queue["pending"].append(item)
    """
    with FileLock(str(_lock_path())):
        queue = _read_raw()
        yield queue
        _write_raw(queue)


def read_queue() -> dict:
    """Read the queue snapshot under a short-held lock.

    Suitable for read-only inspection. The lock is released before returning
    so callers must not assume the data stays current.
    """
    with FileLock(str(_lock_path())):
        return _read_raw()
