# 开发文档

## 本地开发环境搭建

### 前置要求

- Python 3.9+
- Node.js 18+
- pip 和 npm

### Router 开发

```bash
cd router
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .  # 开发模式安装

# 启动开发服务器
python run.py
```

### Plugin 开发

```bash
cd plugin
npm install

# 启动开发服务器
npm run dev
```

## 核心模块说明

### MessageDispatcher (router/core/dispatcher.py)

消息调度器，负责：
- 解析目标 Agent
- 转发消息到对应端点
- 健康检查和状态监控
- 错误处理和重试

### PrefixDetector (plugin/src/lib/prefix-detector.js)

前缀检测器，负责：
- 识别消息前缀
- 提取清理后的内容
- 支持自定义前缀
- 大小写不敏感匹配

### RouterClient (plugin/src/lib/router-client.js)

Router 客户端，负责：
- 与 Router 通信
- 消息序列化
- 错误处理
- 健康检查

## 添加新 Agent

1. 在 `config/default.json` 中添加 Agent 配置
2. 在 `router/core/config.py` 中添加端点
3. 在 `plugin/src/config/default.js` 中添加前缀映射
4. 重启 Router 和 Plugin

## 调试技巧

### Router 调试

```python
# 启用详细日志
export HERMESCLAW_LOG_LEVEL=DEBUG

# 测试单个端点
curl -X POST http://localhost:18889/route \
  -H "Content-Type: application/json" \
  -d '{"content":"test","prefix":"hm"}'
```

### Plugin 调试

```bash
# 查看前缀检测结果
curl http://localhost:3001/config

# 测试消息处理
curl -X POST http://localhost:3001/message \
  -H "Content-Type: application/json" \
  -d '{"content":"hm: hello","userId":"test"}'
```

## 常见问题

### Router 无法启动

1. 检查端口 18889 是否被占用
2. 检查 Python 版本是否 >= 3.9
3. 检查依赖是否安装完整

### Plugin 无法连接 Router

1. 检查 Router 是否运行
2. 检查 `routerEndpoint` 配置
3. 检查防火墙设置

### 消息未正确路由

1. 检查前缀是否正确
2. 检查 Agent 端点是否可达
3. 查看 Router 日志

## 贡献指南

1. Fork 仓库
2. 创建功能分支
3. 提交更改
4. 创建 Pull Request

## 发布流程

### Router 发布

```bash
cd router
python setup.py sdist bdist_wheel
twine upload dist/*
```

### Plugin 发布

```bash
cd plugin
npm version patch
npm publish
```
