#!/bin/bash

# HermesClaw 快速测试脚本

set -e

echo "🧪 HermesClaw 测试"
echo "=================="

# 测试 Router
echo ""
echo "📡 测试 Router..."

ROUTER_HEALTH=$(curl -s http://localhost:18889/health || echo '{"status":"error"}')
if echo "$ROUTER_HEALTH" | grep -q '"status":"ok"'; then
    echo "✅ Router 运行正常"
else
    echo "❌ Router 未运行或异常"
    echo "   响应: $ROUTER_HEALTH"
fi

# 测试 Plugin
echo ""
echo "🔌 测试 Plugin..."

PLUGIN_HEALTH=$(curl -s http://localhost:3001/health || echo '{"status":"error"}')
if echo "$PLUGIN_HEALTH" | grep -q '"status":"ok"'; then
    echo "✅ Plugin 运行正常"
else
    echo "❌ Plugin 未运行或异常"
    echo "   响应: $PLUGIN_HEALTH"
fi

# 测试前缀检测
echo ""
echo "🔍 测试前缀检测..."

TEST_MESSAGES=(
    "hm: test message"
    "gpt: test message"
    "cherry: test message"
    "wb: test message"
    "both: test message"
    "all: test message"
    "oc: test message"
    "no prefix message"
)

for msg in "${TEST_MESSAGES[@]}"; do
    RESPONSE=$(curl -s -X POST http://localhost:3001/message \
        -H "Content-Type: application/json" \
        -d "{\"content\":\"$msg\",\"userId\":\"test\"}" || echo '{"error":"failed"}')
    
    if echo "$RESPONSE" | grep -q '"handled":true'; then
        echo "✅ '$msg' → 已路由"
    elif echo "$RESPONSE" | grep -q '"handled":false'; then
        echo "✅ '$msg' → 本地处理"
    else
        echo "❌ '$msg' → 错误"
        echo "   响应: $RESPONSE"
    fi
done

echo ""
echo "🎉 测试完成"
