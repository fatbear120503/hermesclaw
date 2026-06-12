#!/bin/bash
set -e
echo "=== OpenClaw Gateway Hot Reload ==="
source .env
docker-compose restart
sleep 3
docker-compose ps
echo "=== Gateway reloaded ==="
