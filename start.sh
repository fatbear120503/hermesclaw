#!/bin/bash

echo '🦀 启动 HermesClaw...'

# 启动 Router
echo '📡 启动 Router...'
cd router
source venv/bin/activate
python run.py &
ROUTER_PID=$!
cd ..

# 启动 Plugin
echo '🔌 启动 Plugin...'
cd plugin
npm start &
PLUGIN_PID=$!
cd ..

echo ''
echo '✅ HermesClaw 已启动'
echo '   Router: http://0.0.0.0:18889'
echo '   Plugin: http://localhost:3001'
echo ''
echo '按 Ctrl+C 停止'

trap 'kill $ROUTER_PID $PLUGIN_PID; exit' INT
wait
