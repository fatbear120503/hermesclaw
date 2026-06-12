#!/bin/bash

# HermesClaw 安装脚本
# 支持 macOS 和 Linux

set -e

echo "🦀 HermesClaw 安装程序"
echo "======================="

# 检查系统
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
else
    echo "❌ 不支持的操作系统: $OSTYPE"
    exit 1
fi

echo "📋 检测到系统: $OS"

# 检查依赖
check_dependency() {
    if command -v $1 &> /dev/null; then
        echo "✅ $1 已安装"
        return 0
    else
        echo "❌ $1 未安装"
        return 1
    fi
}

echo ""
echo "🔍 检查依赖..."

MISSING_DEPS=()

if ! check_dependency python3; then
    MISSING_DEPS+=("python3")
fi

if ! check_dependency pip3; then
    MISSING_DEPS+=("pip3")
fi

if ! check_dependency node; then
    MISSING_DEPS+=("node")
fi

if ! check_dependency npm; then
    MISSING_DEPS+=("npm")
fi

if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo ""
    echo "⚠️  缺少以下依赖: ${MISSING_DEPS[*]}"
    echo "请先安装依赖后再运行安装脚本"
    
    if [[ "$OS" == "macos" ]]; then
        echo "💡 建议使用 Homebrew 安装:"
        echo "   brew install python node"
    else
        echo "💡 使用包管理器安装:"
        echo "   sudo apt-get install python3 python3-pip nodejs npm"
    fi
    
    exit 1
fi

# 安装 Router
echo ""
echo "📦 安装 Router..."
cd router
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..

# 安装 Plugin
echo ""
echo "📦 安装 Plugin..."
cd plugin
npm install
cd ..

# 创建启动脚本
echo ""
echo "🚀 创建启动脚本..."

cat > start.sh << 'EOF'
#!/bin/bash

echo "🦀 启动 HermesClaw..."

# 启动 Router
echo "📡 启动 Router..."
cd router
source venv/bin/activate
python run.py &
ROUTER_PID=$!
cd ..

# 启动 Plugin
echo "🔌 启动 Plugin..."
cd plugin
npm start &
PLUGIN_PID=$!
cd ..

echo ""
echo "✅ HermesClaw 已启动"
echo "   Router: http://localhost:18889"
echo "   Plugin: http://localhost:3001"
echo ""
echo "按 Ctrl+C 停止"

# 等待中断
trap "kill $ROUTER_PID $PLUGIN_PID; exit" INT
wait
EOF

chmod +x start.sh

# 创建配置
echo ""
echo "⚙️  创建默认配置..."
if [ ! -f config/.env ]; then
    cp config/.env.example config/.env
    echo "✅ 已创建 config/.env"
fi

echo ""
echo "🎉 安装完成!"
echo ""
echo "使用方式:"
echo "   启动: ./start.sh"
echo "   配置: 编辑 config/.env"
echo "   测试: pytest tests/"
echo ""
echo "文档:"
echo "   README.md       - 项目说明"
echo "   DEVELOPMENT.md  - 开发文档"
