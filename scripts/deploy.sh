#!/bin/bash
# Deploy script for telegram_media_hook

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TARGET_DIR="${OPENCLAW_WORKSPACE:-/home/openclaw/.openclaw/workspace}/telegram_media_hook"

echo "🚀 Deploying telegram_media_hook..."

# Create target directory
echo "📁 Creating target directory: $TARGET_DIR"
mkdir -p "$TARGET_DIR"

# Copy source files
echo "📤 Copying source files..."
rsync -av --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    "$PROJECT_DIR/src/" "$TARGET_DIR/src/"

# Copy config files
echo "📤 Copying config files..."
cp "$PROJECT_DIR/pyproject.toml" "$TARGET_DIR/"
cp "$PROJECT_DIR/README.md" "$TARGET_DIR/"

# Create uploads directory
echo "📤 Creating uploads directory..."
mkdir -p "$TARGET_DIR/uploads"

# Install in workspace venv (if exists)
if [ -d "$HOME/.openclaw/venv" ]; then
    echo "🐍 Installing in OpenClaw venv..."
    source "$HOME/.openclaw/venv/bin/activate"
    pip install -e "$TARGET_DIR"
elif [ -d "$PROJECT_DIR/.venv" ]; then
    echo "🐍 Using project venv..."
    source "$PROJECT_DIR/.venv/bin/activate"
    pip install -e "$TARGET_DIR"
else
    echo "⚠️  No venv found, skipping pip install"
fi

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Target: $TARGET_DIR"
echo ""
echo "Next steps:"
echo "1. Set TELEGRAM_BOT_TOKEN environment variable"
echo "2. Integrate hook with OpenClaw gateway"
echo "3. Run: python -m telegram_media_hook test"
