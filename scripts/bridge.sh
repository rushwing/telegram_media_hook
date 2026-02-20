#!/bin/bash
# OpenClaw Integration Script
# This script reads the message queue and sends messages to OpenClaw

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
QUEUE_FILE="${OPENCLAW_WORKSPACE:-/home/openclaw/.openclaw/workspace}/telegram_media_hook/uploads/message_queue.json"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:18789}"
SESSION_KEY="agent:main:main"

echo "📬 Telegram Media Hook → OpenClaw Bridge"
echo "   Queue: $QUEUE_FILE"
echo "   Gateway: $GATEWAY_URL"
echo ""

# Check if queue file exists
if [ ! -f "$QUEUE_FILE" ]; then
    echo "No queue file found. Run 'serve' first to start polling."
    exit 0
fi

# Function to send message to OpenClaw
send_to_openclaw() {
    local message="$1"
    local media_path="$2"

    # Send via gateway API
    response=$(curl -s -X POST "$GATEWAY_URL/api/sessions/$SESSION_KEY/message" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $GATEWAY_TOKEN" \
        -d "{\"message\": \"$message\"}" 2>/dev/null || echo "")

    if [ -n "$response" ]; then
        echo "  ✅ Sent to OpenClaw"
        return 0
    else
        echo "  ⚠️  Could not send to OpenClaw (check GATEWAY_TOKEN)"
        return 1
    fi
}

# Read and process queue
echo "Checking for pending messages..."

# Use python to parse JSON (more reliable than bash)
python3 << EOF
import json
import os
import subprocess
import sys

queue_file = os.environ.get("QUEUE_FILE", "$QUEUE_FILE")
gateway_url = os.environ.get("GATEWAY_URL", "$GATEWAY_URL")
gateway_token = os.environ.get("GATEWAY_TOKEN", "")

try:
    with open(queue_file, "r") as f:
        queue = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    print("No pending messages")
    sys.exit(0)

pending = [m for m in queue if not m.get("processed", False)]

if not pending:
    print("No pending messages")
    sys.exit(0)

print(f"Found {len(pending)} pending message(s)\n")

for msg in pending:
    print(f"📎 [{msg['id']}]")
    print(f"   Media: {msg['media_path']}")
    print(f"   Text: {msg['rewritten_text'][:60]}...")

    # Try to send to OpenClaw if token is available
    if gateway_token:
        try:
            import urllib.request
            import urllib.error

            data = json.dumps({"message": msg['rewritten_text']}).encode('utf-8')
            req = urllib.request.Request(
                f"{gateway_url}/api/sessions/{'agent:main:main'}/message",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {gateway_token}"
                }
            )
            urllib.request.urlopen(req, timeout=5)
            print("   ✅ Sent to OpenClaw")

            # Mark as processed
            msg['processed'] = True
        except Exception as e:
            print(f"   ⚠️  Could not send: {e}")
    else:
        print("   ℹ️  Set GATEWAY_TOKEN to auto-send to OpenClaw")

    print()

# Write back processed status
with open(queue_file, "w") as f:
    json.dump(queue, f, indent=2)

print("Done!")
EOF
