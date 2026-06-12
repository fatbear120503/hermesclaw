#!/bin/bash
# Start WebSocket Adapter

cd "$(dirname "$0")"
source ../router/venv/bin/activate
python main.py
