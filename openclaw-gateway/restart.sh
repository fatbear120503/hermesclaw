#!/bin/bash
set -e
echo "=== OpenClaw Gateway Restart ==="
docker-compose down
docker-compose build --no-cache
docker-compose up -d
sleep 5
docker-compose ps
echo "=== Gateway restarted ==="
echo "WebSocket: ws://localhost:18888"
