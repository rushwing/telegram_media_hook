"""Telegram Bot API client."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import httpx
from telegram_media_hook.config import get_config


@dataclass
class TelegramFile:
    """Represents a file from Telegram."""
    file_id: str
    file_unique_id: str
    file_path: Optional[str]
    file_size: int


class TelegramClient:
    """Client for interacting with Telegram Bot API."""

    def __init__(self, bot_token: Optional[str] = None):
        """Initialize the Telegram client.

        Args:
            bot_token: Telegram Bot API token. If not provided, uses config.
        """
        self.config = get_config()
        self.bot_token = bot_token or self.config.bot_token
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client. Timeout must exceed Telegram's long-poll timeout."""
        return httpx.AsyncClient(timeout=35.0, proxy=None)

    async def get_file(self, file_id: str) -> TelegramFile:
        """Get file info from Telegram.

        Args:
            file_id: The file_id from the Telegram message.

        Returns:
            TelegramFile object with file information.

        Raises:
            httpx.HTTPStatusError: If the API returns an error.
        """
        async with self._get_client() as client:
            response = await client.get(f"{self.base_url}/getFile", params={
                "file_id": file_id
            })
            response.raise_for_status()
            data = response.json()

            if not data.get("ok"):
                raise ValueError(f"Telegram API error: {data.get('description')}")

            result = data["result"]
            return TelegramFile(
                file_id=result["file_id"],
                file_unique_id=result["file_unique_id"],
                file_path=result.get("file_path"),
                file_size=result.get("file_size", 0),
            )

    async def download_file(self, file_path: str) -> bytes:
        """Download file content from Telegram.

        Args:
            file_path: The file_path from TelegramFile.

        Returns:
            File content as bytes.

        Raises:
            httpx.HTTPStatusError: If the download fails.
        """
        # Construct the full URL for file download
        file_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"

        async with self._get_client() as client:
            response = await client.get(file_url)
            response.raise_for_status()
            return response.content

    async def get_file_info(self, file_id: str) -> tuple[TelegramFile, bytes]:
        """Get file info and download content.

        Args:
            file_id: The file_id from the Telegram message.

        Returns:
            Tuple of (TelegramFile, content_bytes)
        """
        file_info = await self.get_file(file_id)
        content = await self.download_file(file_info.file_path)
        return file_info, content
