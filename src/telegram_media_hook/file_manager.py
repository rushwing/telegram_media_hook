"""File manager for saving Telegram media to workspace."""

import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
import aiofiles
from telegram_media_hook.config import get_config


class FileManager:
    """Manages file storage in the workspace."""

    def __init__(self, upload_dir: Optional[Path] = None):
        """Initialize the file manager.

        Args:
            upload_dir: Directory to save uploads. Uses config if not provided.
        """
        self.config = get_config()
        self.upload_dir = upload_dir or self.config.upload_path

    async def ensure_upload_dir(self) -> None:
        """Ensure the upload directory exists."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def generate_filename(self, original_name: Optional[str] = None) -> str:
        """Generate a unique filename.

        Args:
            original_name: Original filename (optional, for extension).

        Returns:
            Generated filename with UUID.
        """
        # Get extension from original name or default to jpg
        ext = "jpg"
        if original_name:
            parts = original_name.rsplit(".", 1)
            if len(parts) > 1:
                ext = parts[1].lower()

        # Generate unique name with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"{timestamp}_{unique_id}.{ext}"

    def get_file_path(self, filename: str) -> Path:
        """Get the full path for a file.

        Args:
            filename: The filename.

        Returns:
            Full path to the file.
        """
        return self.upload_dir / filename

    async def save_file(self, content: bytes, filename: str) -> Path:
        """Save file content to disk.

        Args:
            content: File content as bytes.
            filename: Filename to save as.

        Returns:
            Path to the saved file.
        """
        await self.ensure_upload_dir()
        file_path = self.get_file_path(filename)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        return file_path

    def get_workspace_relative_path(self, file_path: Path) -> str:
        """Get workspace-relative path.

        Args:
            file_path: Full path to the file.

        Returns:
            Relative path from workspace root.
        """
        try:
            return str(file_path.relative_to(self.config.workspace_root))
        except ValueError:
            # If not relative, return the full path
            return str(file_path)

    def get_upload_dir(self) -> Path:
        """Get the upload directory path."""
        return self.upload_dir

    def cleanup_old_files(self, max_age_days: int = 30) -> int:
        """Clean up old uploaded files.

        Args:
            max_age_days: Maximum age of files to keep.

        Returns:
            Number of files deleted.
        """
        import time
        if not self.upload_dir.exists():
            return 0

        cutoff = time.time() - (max_age_days * 24 * 60 * 60)
        deleted = 0

        for file_path in self.upload_dir.iterdir():
            if file_path.is_file():
                if file_path.stat().st_mtime < cutoff:
                    file_path.unlink()
                    deleted += 1

        return deleted
