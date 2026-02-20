"""OpenClaw Gateway Integration Example.

This module shows how to integrate the Telegram Media Hook
with the OpenClaw gateway.

Usage:
1. Place this file in your OpenClaw extensions directory
2. Or import and call process_message in your gateway hooks
"""

import json
import logging
from typing import Any, Optional
from telegram_media_hook import TelegramMediaHook, process_telegram_update

logger = logging.getLogger(__name__)


class OpenClawTelegramMediaPlugin:
    """Plugin for integrating Telegram Media Hook with OpenClaw."""

    def __init__(self):
        self.hook = TelegramMediaHook()

    async def on_telegram_update(
        self,
        update: dict[str, Any]
    ) -> dict[str, Any]:
        """Process a Telegram update and handle any media.

        This is called by the OpenClaw gateway when a Telegram
        update is received.

        Args:
            update: The raw Telegram update.

        Returns:
            The modified update with rewritten message content.
        """
        try:
            result = await self.hook.handle_update(update)

            if result and result.rewritten_message:
                # Update the message text with the rewritten version
                if "message" in update:
                    update["message"]["text"] = result.rewritten_message
                    logger.info(
                        f"Rewrote message with media path: "
                        f"{result.media_info.workspace_path}"
                    )

                # Also store the media info for skills to access
                if result.media_info:
                    update["_telegram_media"] = {
                        "file_path": result.media_info.file_path,
                        "workspace_path": result.media_info.workspace_path,
                        "file_type": result.media_info.file_type,
                    }

        except Exception as e:
            logger.error(f"Error processing Telegram media: {e}")
            # Don't crash on errors - let the message through

        return update

    async def on_message_created(
        self,
        message: dict[str, Any],
        channel: str
    ) -> dict[str, Any]:
        """Hook called when a message is created.

        Args:
            message: The message data.
            channel: The channel (telegram, whatsapp, etc.)

        Returns:
            The (possibly modified) message.
        """
        if channel != "telegram":
            return message

        # Check if this is a Telegram update format
        if "photo" in message or "document" in message:
            # Wrap in update format for the hook
            update = {"message": message}
            result = await self.hook.handle_update(update)

            if result:
                message["text"] = result.rewritten_message

        return message


# Singleton instance for use in gateway
_plugin: Optional[OpenClawTelegramMediaPlugin] = None


def get_plugin() -> OpenClawTelegramMediaPlugin:
    """Get the plugin singleton."""
    global _plugin
    if _plugin is None:
        _plugin = OpenClawTelegramMediaPlugin()
    return _plugin


# Example usage in an OpenClaw gateway hook:
"""
# In your gateway code:

from telegram_media_hook_integration import get_plugin

async def handle_telegram_update(update):
    plugin = get_plugin()
    return await plugin.on_telegram_update(update)

# The gateway will call this for each Telegram update,
# and the message will be rewritten to include the local
# file path for any uploaded images.
"""


# Example: How the skill would use the uploaded image
"""
# In your SKILL.md or skill code:

When you receive a message like:
  "用户上传了图片: workspace/uploads/20260220_143256_abc123.jpg"

1. Extract the file path from the message
2. Read the image:
   image_path = "/home/openclaw/.openclaw/workspace/uploads/20260220_143256_abc123.jpg"
   with open(image_path, "rb") as f:
       image_data = f.read()

3. Process with your AI model (Vision API, etc.)
"""
