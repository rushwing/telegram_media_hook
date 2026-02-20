"""Main hook implementation for OpenClaw integration."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional
from telegram_media_hook.config import get_config, Config
from telegram_media_hook.telegram_client import TelegramClient
from telegram_media_hook.file_manager import FileManager

logger = logging.getLogger(__name__)


@dataclass
class MediaInfo:
    """Information about processed media."""
    file_id: str
    file_path: str
    workspace_path: str
    file_type: str  # "photo", "document", etc.


@dataclass
class ProcessedMessage:
    """A message after processing by the hook."""
    original_message: str
    media_info: Optional[MediaInfo] = None
    rewritten_message: Optional[str] = None


class TelegramMediaHook:
    """Hook for processing Telegram media in OpenClaw.

    This hook intercepts Telegram messages with media attachments,
    downloads them, saves to workspace, and rewrites the message
    to include the local file path.
    """

    def __init__(self, config: Optional[Config] = None):
        """Initialize the hook.

        Args:
            config: Configuration. Uses default if not provided.
        """
        self.config = config or get_config()
        self.telegram_client = TelegramClient()
        self.file_manager = FileManager()

    async def process_message(self, message_data: dict[str, Any]) -> ProcessedMessage:
        """Process a Telegram message and handle any media.

        Args:
            message_data: The raw message data from Telegram update.

        Returns:
            ProcessedMessage with media info and rewritten content.
        """
        # Extract message text
        original_text = message_data.get("text") or message_data.get("caption") or ""
        message_id = message_data.get("message_id", "unknown")

        # Check for media
        media_info = None

        # Check for photo
        if "photo" in message_data:
            photos = message_data["photo"]
            if photos:
                # Get the largest photo
                photo = photos[-1]
                media_info = await self._process_photo(
                    photo.get("file_id"),
                    message_id
                )

        # Check for document
        elif "document" in message_data:
            doc = message_data["document"]
            media_info = await self._process_document(
                doc.get("file_id"),
                doc.get("file_name"),
                message_id
            )

        # Build rewritten message
        rewritten = original_text
        if media_info:
            # Add media info to message
            media_line = f"\n\n📎 用户上传了图片: {media_info.workspace_path}"
            rewritten = original_text + media_line

        return ProcessedMessage(
            original_message=original_text,
            media_info=media_info,
            rewritten_message=rewritten,
        )

    async def _process_photo(
        self,
        file_id: str,
        message_id: str
    ) -> MediaInfo:
        """Process a photo from Telegram.

        Args:
            file_id: Telegram file_id.
            message_id: Message ID for logging.

        Returns:
            MediaInfo about the saved file.
        """
        logger.info(f"Processing photo from message {message_id}")

        # Download file
        file_info, content = await self.telegram_client.get_file_info(file_id)

        # Generate filename
        filename = self.file_manager.generate_filename("photo.jpg")

        # Save to disk
        file_path = await self.file_manager.save_file(content, filename)
        workspace_path = self.file_manager.get_workspace_relative_path(file_path)

        logger.info(f"Saved photo to {file_path}")

        return MediaInfo(
            file_id=file_id,
            file_path=str(file_path),
            workspace_path=workspace_path,
            file_type="photo",
        )

    async def _process_document(
        self,
        file_id: str,
        original_filename: Optional[str],
        message_id: str
    ) -> MediaInfo:
        """Process a document from Telegram.

        Args:
            file_id: Telegram file_id.
            original_filename: Original filename from Telegram.
            message_id: Message ID for logging.

        Returns:
            MediaInfo about the saved file.
        """
        logger.info(f"Processing document from message {message_id}")

        # Download file
        file_info, content = await self.telegram_client.get_file_info(file_id)

        # Generate filename (preserve extension)
        filename = self.file_manager.generate_filename(original_filename or "document")

        # Save to disk
        file_path = await self.file_manager.save_file(content, filename)
        workspace_path = self.file_manager.get_workspace_relative_path(file_path)

        logger.info(f"Saved document to {file_path}")

        return MediaInfo(
            file_id=file_id,
            file_path=str(file_path),
            workspace_path=workspace_path,
            file_type="document",
        )

    async def handle_update(self, update: dict[str, Any]) -> Optional[ProcessedMessage]:
        """Handle a Telegram update.

        Args:
            update: The raw update from Telegram.

        Returns:
            ProcessedMessage if media was found, None otherwise.
        """
        # Extract message from update
        message = update.get("message")
        if not message:
            # Also check for edited_message
            message = update.get("edited_message")

        if not message:
            return None

        # Check if there's media
        has_photo = "photo" in message
        has_document = "document" in message

        if not has_photo and not has_document:
            return None

        # Process the message
        return await self.process_message(message)


# Standalone function for easy integration
async def process_telegram_update(update: dict[str, Any]) -> Optional[ProcessedMessage]:
    """Process a Telegram update and handle any media.

    This is the main entry point for the hook.

    Args:
        update: The raw update from Telegram Bot API.

    Returns:
        ProcessedMessage if media was found, None otherwise.
    """
    hook = TelegramMediaHook()
    return await hook.handle_update(update)


# For testing
if __name__ == "__main__":
    import asyncio

    async def test():
        """Test the hook with a sample update."""
        # Sample photo update
        test_update = {
            "update_id": 123456789,
            "message": {
                "message_id": 1,
                "from": {"id": 123, "is_bot": False, "first_name": "Test"},
                "chat": {"id": 123, "type": "private"},
                "date": 1234567890,
                "photo": [
                    {"file_id": "test", "file_unique_id": "test", "file_size": 1000},
                ],
                "text": "Test message",
            }
        }

        hook = TelegramMediaHook()
        result = await hook.handle_update(test_update)
        print(json.dumps(result, default=str, indent=2))

    asyncio.run(test())
