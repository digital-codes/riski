#!/bin/bash
# repo root = directory containing this script's parent (portable)
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT=11384
APP="src.apiServer:app"

echo "Stopping existing API process on port $PORT..."
pkill -f "uvicorn.*$APP.*$PORT" 2>/dev/null
sleep 2

echo "Starting API on http://127.0.0.1:$PORT..."
cd "$REPO_DIR"
PYTHON="${PYTHON:-$(command -v python3)}"
setsid "$PYTHON" -m uvicorn "$APP" --host 127.0.0.1 --port "$PORT" </dev/null > "$REPO_DIR/apiServer.log" 2>&1 &
echo "PID: $!"
sleep 3
curl -s "http://127.0.0.1:$PORT/health"
echo
