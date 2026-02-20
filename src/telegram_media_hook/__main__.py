"""CLI for Telegram Media Hook."""

import asyncio
import logging
import sys
import json
import click
from pathlib import Path
from telegram_media_hook.config import get_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """Telegram Media Hook CLI."""
    pass


@cli.command()
def test():
    """Test the hook configuration."""
    config = get_config()

    is_valid, error = config.validate()

    if is_valid:
        click.echo(f"✅ Configuration valid")
        click.echo(f"   Workspace: {config.workspace_root}")
        click.echo(f"   Upload dir: {config.upload_path}")
    else:
        click.echo(f"❌ Configuration error: {error}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("update_file", type=click.Path(exists=True))
def process(update_file: str):
    """Process a Telegram update from file."""
    async def run():
        with open(update_file) as f:
            update = json.load(f)

        from telegram_media_hook import TelegramMediaHook
        hook = TelegramMediaHook()
        result = await hook.handle_update(update)

        if result:
            print(json.dumps(result, default=str, indent=2))
        else:
            print("No media found in update")

    asyncio.run(run())


@cli.command()
@click.option("--port", default=8081, help="Port to listen on")
def queue_server(port: int):
    """Start the queue API server.
    
    Gateway calls this to add file_ids to the queue.
    """
    from telegram_media_hook.queue_api import run_server
    click.echo(f"🚀 Starting queue API server on http://127.0.0.1:{port}")
    click.echo(f"   Add to queue: POST /add")
    click.echo(f"   Status: GET /status")
    run_server(port)


@cli.command()
def mcp():
    """Start the MCP server."""
    from telegram_media_hook.mcp_server import main
    main()


@cli.command()
@click.argument("file_id")
@click.option("--message-id", default=0, type=int)
@click.option("--chat-id", default=0, type=int)
@click.option("--caption", default="")
def queue_add(file_id: str, message_id: int, chat_id: int, caption: str):
    """Manually add a file_id to the queue."""
    from telegram_media_hook.mcp_server import add_to_queue
    
    async def run():
        result = await add_to_queue(file_id, message_id, chat_id, caption)
        print(json.dumps(result, indent=2))
    
    asyncio.run(run())


@cli.command()
def queue_status():
    """Show queue status."""
    from telegram_media_hook.mcp_server import list_pending_media
    
    async def run():
        result = await list_pending_media()
        print(json.dumps(result, indent=2))
    
    asyncio.run(run())


@cli.command()
@click.option("--max-age", default=30, help="Maximum age in days")
def cleanup(max_age: int):
    """Clean up old uploaded files."""
    from telegram_media_hook.file_manager import FileManager

    file_manager = FileManager()
    deleted = file_manager.cleanup_old_files(max_age)
    click.echo(f"Deleted {deleted} old files")


if __name__ == "__main__":
    cli()
