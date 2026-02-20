#!/bin/bash
# Build script for telegram_media_hook

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "📦 Building telegram_media_hook..."

cd "$PROJECT_DIR"

# Build the package
echo "🔨 Creating wheel..."
uv build

# Or use pip for building
# pip install build
# python -m build

echo "✅ Build complete!"
echo ""
echo "Wheel location: dist/"
ls -la dist/
