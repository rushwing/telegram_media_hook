#!/bin/bash
# Integration test script for telegram_media_hook

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🧪 Running integration tests..."

cd "$PROJECT_DIR"

# Check if venv exists, create if not
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    uv venv .venv
fi

# Activate venv
echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# Install package
echo "📥 Installing package..."
pip install -e .

# Install test dependencies
echo "📥 Installing test dependencies..."
pip install pytest pytest-asyncio pytest-cov httpx

# Run tests
echo "🏃 Running tests..."
python -m pytest -v --cov=telegram_media_hook --cov-report=term-missing

echo ""
echo "✅ Tests complete!"
