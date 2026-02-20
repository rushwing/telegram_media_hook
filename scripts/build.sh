#!/bin/bash
# Build telegram-media-hook into a distributable wheel.
# Output: dist/telegram_media_hook-*.whl

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Building telegram-media-hook MCP server..."

# Clean previous build artifacts
rm -rf dist/ build/

# Build wheel + sdist
uv build

echo ""
echo "Build complete:"
ls -lh dist/
echo ""
echo "Deploy to Raspberry Pi with:"
echo "  PI_HOST=pi@raspberrypi.local \\"
echo "  TELEGRAM_BOT_TOKEN=<token> \\"
echo "  ./scripts/deploy.sh"
