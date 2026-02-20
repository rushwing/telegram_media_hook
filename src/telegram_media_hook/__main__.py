"""CLI for Telegram Media Hook."""

import asyncio
import logging
import sys
import json
import click
from pathlib import Path
from telegram_media_hook.config import get_config
from telegram_media_hook.webhook_server import run_server, WebhookServer
from telegram_media_hook.queue_service import MessageQueue

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
        click.echo(f"   Queue file: {config.queue_path}")

        # Check .env file
        env_file = config.workspace_root.parent / "telegram_media_hook" / ".env"
        if not env_file.exists():
            env_file = Path.cwd() / ".env"

        if env_file.exists():
            click.echo(f"   .env file: {env_file}")
        else:
            click.echo(f"   ⚠️  .env file not found, using .env.example")
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
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8080, help="Port to bind to")
def webhook(host: str, port: int):
    """Start the webhook server."""
    click.echo(f"🚀 Starting webhook server on http://{host}:{port}")
    click.echo(f"📬 Telegram will send updates to: http://{host}:{port}/webhook")
    click.echo(f"💚 Health check: http://{host}:{port}/health")
    click.echo("")
    click.echo("To set Telegram webhook, run:")
    click.echo(f"  curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \\")
    click.echo(f"    -d url=https://your-public-url/webhook")
    click.echo("")
    click.echo("Press Ctrl+C to stop")

    async def run():
        await run_server()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        click.echo("\n👋 Server stopped")


@cli.command()
@click.argument("webhook_url")
def setup_webhook(webhook_url: str):
    """Setup Telegram webhook (prints curl command)."""
    config = get_config()
    
    if not config.bot_token:
        click.echo("❌ TELEGRAM_BOT_TOKEN not set in .env", err=True)
        sys.exit(1)

    click.echo("Run this command to set the webhook:")
    click.echo("")
    click.echo(f"curl -X POST https://api.telegram.org/bot{config.bot_token}/setWebhook \\")
    click.echo(f"  -d url={webhook_url}")
    click.echo("")
    click.echo("To remove webhook:")
    click.echo(f"curl -X POST https://api.telegram.org/bot{config.bot_token}/deleteWebhook")


@cli.command()
def queue_status():
    """Show webhook queue status."""
    async def run():
        server = WebhookServer()
        pending = await server.queue.get_pending()
        
        if not pending:
            click.echo("No pending updates")
            return

        click.echo(f"📬 Pending updates: {len(pending)}\n")
        for item in pending:
            status = item.get("status", "unknown")
            msg = item.get("update", {}).get("message", {})
            click.echo(f"  [{status}] {msg.get('text', 'No text')[:50]}")

    asyncio.run(run())


@cli.command()
@click.option("--max-age", default=30, help="Maximum age in days")
def cleanup(max_age: int):
    """Clean up old uploaded files."""
    from telegram_media_hook.file_manager import FileManager

    file_manager = FileManager()
    deleted = file_manager.cleanup_old_files(max_age)
    click.echo(f"Deleted {deleted} old files")

    # Also clean up queue
    queue = MessageQueue()
    queue_deleted = queue.cleanup_processed(max_age * 24)
    click.echo(f"Cleaned up {queue_deleted} processed queue entries")


@cli.command()
def init():
    """Initialize .env file from .env.example."""
    config = get_config()
    env_path = config.workspace_root.parent / "telegram_media_hook" / ".env"
    example_path = env_path.parent / ".env.example"

    if not example_path.exists():
        example_path = Path.cwd() / ".env.example"

    if env_path.exists():
        click.echo(f"⚠️  .env already exists at {env_path}")
        return

    if example_path.exists():
        import shutil
        shutil.copy(example_path, env_path)
        click.echo(f"✅ Created .env from .env.example")
        click.echo(f"   Edit {env_path} with your Telegram Bot Token")
    else:
        click.echo(f"❌ .env.example not found", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
