"""Telegram Media Hook for OpenClaw.

This module provides a hook that intercepts Telegram messages with media,
downloads the files, and rewrites the message to include the local file path.
"""

__version__ = "0.1.0"

from telegram_media_hook.hook import TelegramMediaHook

__all__ = ["TelegramMediaHook"]
