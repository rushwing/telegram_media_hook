#!/bin/bash
# Deploy telegram-media-hook MCP server to Raspberry Pi.
#
# Required env vars:
#   PI_HOST              SSH target, e.g. pi@raspberrypi.local
#   TELEGRAM_BOT_TOKEN   Bot token from @BotFather
#
# Optional env vars:
#   OPENCLAW_WORKSPACE   Workspace path on Pi (default: ~/openclaw/workspace)
#
# Usage:
#   PI_HOST=pi@raspberrypi.local \
#   TELEGRAM_BOT_TOKEN=123:abc \
#   ./scripts/deploy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env if present (for TELEGRAM_BOT_TOKEN etc.)
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

# Validate required vars
: "${PI_HOST:?PI_HOST is required (e.g. pi@raspberrypi.local)}"
: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required}"

OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE:-/home/openclaw/.openclaw/workspace}"
OPENCLAW_CONFIG="~/.openclaw/openclaw.json"

# Find the latest wheel in dist/
WHEEL=$(ls "$PROJECT_DIR"/dist/*.whl 2>/dev/null | sort -V | tail -1)
if [ -z "$WHEEL" ]; then
    echo "No wheel found in dist/. Run ./scripts/build.sh first."
    exit 1
fi

WHEEL_FILE=$(basename "$WHEEL")
echo "Deploying $WHEEL_FILE → $PI_HOST"
echo ""

# ── Step 1: Copy wheel to Pi ──────────────────────────────────────────────────
echo "[1/3] Copying wheel to Pi..."
scp "$WHEEL" "$PI_HOST:/tmp/$WHEEL_FILE"

# ── Step 2: Install on Pi via uv tool ────────────────────────────────────────
echo "[2/3] Installing MCP server on Pi..."
ssh "$PI_HOST" "uv tool install /tmp/$WHEEL_FILE --force && rm /tmp/$WHEEL_FILE"

# ── Step 3: Register in openclaw.json ────────────────────────────────────────
echo "[3/3] Registering in openclaw.json..."

# Build the mcpServers entry locally and pipe it safely to the Pi
MCP_ENTRY=$(python3 - <<PYEOF
import json
entry = {
    "command": "telegram-media-hook-mcp",
    "env": {
        "TELEGRAM_BOT_TOKEN": "$TELEGRAM_BOT_TOKEN",
        "OPENCLAW_WORKSPACE": "$OPENCLAW_WORKSPACE",
    },
}
print(json.dumps(entry))
PYEOF
)

ssh "$PI_HOST" "python3 -c \"
import json, os, sys

entry = json.loads(sys.stdin.read())
config_path = os.path.expanduser('$OPENCLAW_CONFIG')

if not os.path.exists(config_path):
    print('openclaw.json not found at', config_path)
    sys.exit(1)

with open(config_path) as f:
    config = json.load(f)

config.setdefault('mcpServers', {})['telegram-media'] = entry

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)

print('Registered telegram-media in mcpServers')
\"" <<< "$MCP_ENTRY"

echo ""
echo "Done. Restart OpenClaw on the Pi to load the MCP server."
echo ""
echo "To verify the tool is available, ask OpenClaw:"
echo "  'what MCP tools do you have?'"
