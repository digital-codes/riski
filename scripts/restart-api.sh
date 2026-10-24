#!/bin/bash
REPO_DIR="/home/okl/projects/riski"
PORT=11384
APP="src.apiServer:app"

echo "Stopping existing API process on port $PORT..."
pkill -f "uvicorn.*$APP.*$PORT" 2>/dev/null
sleep 2

echo "Starting API on http://127.0.0.1:$PORT..."
cd "$REPO_DIR"
setsid /usr/bin/python3 -m uvicorn "$APP" --host 127.0.0.1 --port "$PORT" </dev/null > "$REPO_DIR/apiServer.log" 2>&1 &
echo "PID: $!"
sleep 3
curl -s "http://127.0.0.1:$PORT/health"
echo
