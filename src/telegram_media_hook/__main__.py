"""CLI for Telegram Media Hook."""

import asyncio
import json
import logging
import sys

import click

from telegram_media_hook.config import get_config
from telegram_media_hook.queue_service import MessageQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """Telegram Media Hook CLI."""
    pass


@cli.command()
def serve():
    """Start the MCP server (stdio transport for OpenClaw)."""
    from telegram_media_hook.mcp_server import main
    main()


@cli.command()
def test():
    """Test the hook configuration."""
    config = get_config()
    is_valid, error = config.validate()

    if is_valid:
        click.echo("✅ Configuration valid")
        click.echo(f"   Workspace: {config.workspace_root}")
        click.echo(f"   Upload dir: {config.upload_path}")
        click.echo(f"   Queue file: {config.queue_path}")
    else:
        click.echo(f"❌ Configuration error: {error}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("update_file", type=click.Path(exists=True))
def process(update_file: str):
    """Process a Telegram update from a JSON file (for testing)."""
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
@click.option("--max-age", default=30, help="Maximum file age in days")
def cleanup(max_age: int):
    """Clean up old uploaded files and processed queue entries."""
    from telegram_media_hook.file_manager import FileManager

    file_manager = FileManager()
    deleted = file_manager.cleanup_old_files(max_age)
    click.echo(f"Deleted {deleted} old files")

    queue = MessageQueue()
    queue_deleted = queue.cleanup_processed(max_age * 24)
    click.echo(f"Cleaned up {queue_deleted} processed queue entries")


@cli.command()
def init():
    """Initialize .env file from .env.example."""
    import shutil
    from pathlib import Path

    config = get_config()
    env_path = config.workspace_root.parent / "telegram_media_hook" / ".env"
    example_path = env_path.parent / ".env.example"

    if not example_path.exists():
        example_path = Path.cwd() / ".env.example"

    if env_path.exists():
        click.echo(f"⚠️  .env already exists at {env_path}")
        return

    if example_path.exists():
        shutil.copy(example_path, env_path)
        click.echo("✅ Created .env from .env.example")
        click.echo(f"   Edit {env_path} with your Telegram Bot Token")
    else:
        click.echo("❌ .env.example not found", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
