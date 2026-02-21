"""MCP server for Telegram media hook."""

import logging

from mcp.server.fastmcp import FastMCP

from telegram_media_hook.config import get_config

logger = logging.getLogger(__name__)

mcp = FastMCP("telegram-media-hook")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
