#!/bin/bash
# ═══════════════════════════════════════════════════════
# HermesClaw v1.0 - 安装脚本
# ═══════════════════════════════════════════════════════

set -e

echo "🐿️  HermesClaw v1.0 安装程序"
echo "=============================="
echo ""

# 检测系统
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
else
    OS="linux"
fi

echo "📋 系统: $OS"
echo ""

# 检查 Python
check_python() {
    python3 --version > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "❌ Python 3 未安装"
        echo "   macOS: brew install python"
        exit 1
    fi
    echo "✅ Python $(python3 --version)"
}

check_python

# 安装依赖
echo ""
echo "📦 安装依赖..."
pip3 install -q qrcode[pil] 2>/dev/null || echo "⚠️ qrcode 可选，稍后扫码功能可能不可用"

echo "✅ 依赖安装完成"

# 设置权限
echo ""
echo "🔐 设置权限..."
chmod +x bin/hermesclaw
chmod +x scripts/setup.py
chmod +x scripts/wechat_qr.py
chmod +x scripts-v3/dispatch.py
echo "✅ 权限设置完成"

# 首次配置引导
echo ""
echo "🚀 启动配置向导..."
printf "
would you like to run the setup wizard now? [Y/n]: "
read -r response
if [[ "$response" =~ ^([nN][oO]|[nN])$ ]]; then
    echo ""
    echo "💡 跳过向导。稍后运行: hermesclaw install"
else
    python3 scripts/setup.py install
fi

echo ""
echo "🎉 HermesClaw v1.0 安装完成！"
echo ""
echo "使用方法:"
echo "   hermesclaw help       → 查看帮助"
echo "   hermesclaw install    → 配置智能体"
echo "   hermesclaw add        → 添加新智能体"
echo "   hermesclaw list       → 列出已配置"
echo "   hermesclaw qrcode     → 生成微信二维码"
echo "   hermesclaw test       → 测试 all: 模式"
echo ""
