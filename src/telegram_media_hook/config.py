"""Configuration for Telegram Media Hook."""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv


def find_env_file() -> Path:
    """Find the .env file in the project directory."""
    # Check current directory first
    current = Path.cwd() / ".env"
    if current.exists():
        return current

    # Check script directory
    script_dir = Path(__file__).parent.parent.parent
    env_file = script_dir / ".env"
    if env_file.exists():
        return env_file

    # Check workspace telegram_media_hook directory
    workspace = Path("/home/openclaw/.openclaw/workspace/telegram_media_hook")
    env_file = workspace / ".env"
    if env_file.exists():
        return env_file

    # Return default location for creation
    return script_dir / ".env"


@dataclass
class Config:
    """Configuration for the Telegram Media Hook."""

    # Telegram Bot Token
    bot_token: str = ""

    # Workspace root directory
    workspace_root: Path = Path("/home/openclaw/.openclaw/workspace")

    # Upload directory (relative to workspace)
    upload_dir: str = "uploads"

    # File size limits
    max_file_size_mb: int = 20

    # Telegram polling interval
    poll_interval: int = 1

    # Queue file for OpenClaw integration
    queue_file: str = "uploads/message_queue.json"

    @property
    def upload_path(self) -> Path:
        """Get the full upload directory path."""
        return self.workspace_root / self.upload_dir

    @property
    def queue_path(self) -> Path:
        """Get the full queue file path."""
        return self.workspace_root / self.queue_file

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from .env file."""
        # Try to load from .env file
        env_path = find_env_file()
        if env_path.exists():
            load_dotenv(env_path)
        elif os.getenv("TELEGRAM_BOT_TOKEN"):
            # Fall back to environment variables if .env doesn't exist
            pass
        else:
            # Create .env from example if it doesn't exist
            example_path = env_path.parent / ".env.example"
            if example_path.exists():
                load_dotenv(example_path)

        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            workspace_root=Path(os.getenv(
                "OPENCLAW_WORKSPACE",
                "/home/openclaw/.openclaw/workspace"
            )),
            upload_dir=os.getenv("UPLOAD_DIR", "uploads"),
            max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "20")),
            poll_interval=int(os.getenv("POLL_INTERVAL", "1")),
            queue_file=os.getenv("QUEUE_FILE", "uploads/message_queue.json"),
        )

    def validate(self) -> tuple[bool, Optional[str]]:
        """Validate the configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.bot_token:
            return False, "TELEGRAM_BOT_TOKEN is not set"

        if not self.workspace_root.exists():
            return False, f"Workspace root does not exist: {self.workspace_root}"

        return True, None


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_config(config: Config) -> None:
    """Set the global config instance."""
    global _config
    _config = config
