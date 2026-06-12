#!/bin/bash
# OpenClaw Gateway 一键安装脚本
# 固定安装路径: /Users/bh1gmj/Documents/kimi/workspace/hermesclaw/openclaw-gateway

set -e

PROJECT_DIR="/Users/bh1gmj/Documents/kimi/workspace/hermesclaw/openclaw-gateway"

echo "=== OpenClaw Gateway 安装 ==="
echo "目标路径: ${PROJECT_DIR}"

# 创建目录
mkdir -p ${PROJECT_DIR}/openclaw
cd ${PROJECT_DIR}

echo "[1/12] Creating openclaw/__init__.py..."
cat > openclaw/__init__.py << 'PYEOF'
"""OpenClaw Gateway - Multi-platform AI router via WebSocket"""
__version__ = "1.0.0"
PYEOF

echo "[2/12] Creating openclaw/router.py..."
cat > openclaw/router.py << 'PYEOF'
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Optional
import aiohttp
import asyncio
import json

@dataclass
class PlatformConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0
    headers: dict = field(default_factory=dict)
    custom_payload: Optional[Callable] = None

class MultiPlatformRouter:
    def __init__(self):
        self.platforms = {}
        self._sessions = {}

    def register(self, prefix, config):
        if not prefix.endswith(":"):
            prefix += ":"
        self.platforms[prefix] = config
        headers = {"Authorization": "Bearer " + config.api_key}
        headers.update(config.headers)
        self._sessions[prefix] = aiohttp.ClientSession(
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=config.timeout)
        )

    async def chat(self, prefix, messages, stream=True):
        if prefix == "all:":
            tasks = [self._stream_platform(pfx, cfg, messages) for pfx, cfg in self.platforms.items()]
            async for result in self._merge_streams(tasks, list(self.platforms.keys())):
                yield result
            return
        if prefix not in self.platforms:
            raise ValueError("Unknown prefix: " + prefix + ". Registered: " + str(list(self.platforms.keys())))
        cfg = self.platforms[prefix]
        async for token in self._stream_platform(prefix, cfg, messages):
            yield (cfg.name, token)

    async def _stream_platform(self, prefix, cfg, messages):
        if cfg.custom_payload:
            payload = cfg.custom_payload(messages)
        else:
            payload = {"model": cfg.model, "messages": messages, "stream": True}
        session = self._sessions[prefix]
        async with session.post(cfg.base_url + "/v1/chat/completions", json=payload) as resp:
            if resp.status == 401:
                raise AuthError(cfg.name + ": API key invalid")
            if resp.status == 429:
                raise RateLimitError(cfg.name + ": Rate limited")
            resp.raise_for_status()
            async for line in resp.content:
                line = line.decode().strip()
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta:
                        yield (cfg.name, delta["content"])
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    async def _merge_streams(self, tasks, platform_keys):
        queues = {key: asyncio.Queue() for key in platform_keys}
        async def producer(task, key):
            async for name, token in task:
                await queues[key].put(("token", name, token))
            await queues[key].put(("done", key, None))
        producers = [asyncio.create_task(producer(task, key)) for task, key in zip(tasks, platform_keys)]
        active = set(platform_keys)
        while active:
            for key in list(active):
                try:
                    msg_type, name, data = queues[key].get_nowait()
                    if msg_type == "done":
                        active.remove(key)
                    else:
                        yield (name, data)
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.01)
        for p in producers:
            p.cancel()

    def list_platforms(self):
        return list(self.platforms.keys())

    async def close(self):
        for s in self._sessions.values():
            await s.close()

class AuthError(Exception): pass
class RateLimitError(Exception): pass
PYEOF

echo "[3/12] Creating openclaw/squirrel.py..."
cat > openclaw/squirrel.py << 'PYEOF'
import json
from typing import AsyncIterator
import aiohttp

class SquirrelAgent:
    def __init__(self, backend="ollama", base_url="http://localhost:11434", model="deepseek-r1:8b"):
        self.backend = backend
        self.base_url = base_url
        self.model = model

    async def chat(self, content, context=None):
        messages = self._build_messages(content, context)
        if self.backend == "ollama":
            return await self._chat_ollama(messages)
        elif self.backend == "http":
            return await self._chat_http(messages)
        else:
            raise ValueError("Unknown backend: " + self.backend)

    async def chat_stream(self, content, context=None):
        messages = self._build_messages(content, context)
        if self.backend == "ollama":
            async for token in self._stream_ollama(messages):
                yield token
        elif self.backend == "http":
            async for token in self._stream_http(messages):
                yield token

    def _build_messages(self, content, context=None):
        messages = []
        if context and context.get("history"):
            messages.extend(context["history"])
        messages.append({"role": "user", "content": content})
        return messages

    async def _chat_ollama(self, messages):
        payload = {"model": self.model, "messages": messages, "stream": False}
        async with aiohttp.ClientSession() as s:
            async with s.post(self.base_url + "/api/chat", json=payload) as resp:
                data = await resp.json()
                return data["message"]["content"]

    async def _stream_ollama(self, messages):
        payload = {"model": self.model, "messages": messages, "stream": True}
        async with aiohttp.ClientSession() as s:
            async with s.post(self.base_url + "/api/chat", json=payload) as resp:
                async for line in resp.content:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content")
                    if content:
                        yield content
                    if data.get("done"):
                        break

    async def _chat_http(self, messages):
        payload = {"model": self.model, "messages": messages, "stream": False}
        async with aiohttp.ClientSession() as s:
            async with s.post(self.base_url + "/v1/chat/completions", json=payload) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def _stream_http(self, messages):
        payload = {"model": self.model, "messages": messages, "stream": True}
        async with aiohttp.ClientSession() as s:
            async with s.post(self.base_url + "/v1/chat/completions", json=payload) as resp:
                async for line in resp.content:
                    line = line.decode().strip()
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            content = chunk["choices"][0].get("delta", {}).get("content")
                            if content:
                                yield content
                        except:
                            continue
PYEOF

echo "[4/12] Creating openclaw/config.py..."
cat > openclaw/config.py << 'PYEOF'
import os
from openclaw.router import MultiPlatformRouter, PlatformConfig

def create_router():
    router = MultiPlatformRouter()
    
    router.register("hm:", PlatformConfig(
        name="SenseNova",
        base_url="https://api.sensenova.cn/v1",
        api_key=os.getenv("SENSENOVA_API_KEY", ""),
        model="SenseNova-6.7-Flash-Lite",
    ))
    
    router.register("gpt:", PlatformConfig(
        name="CherryStudio",
        base_url=os.getenv("CHERRY_BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("CHERRY_API_KEY", ""),
        model=os.getenv("CHERRY_MODEL", "gpt-4o"),
    ))
    
    return router
PYEOF

echo "[5/12] Creating openclaw/gateway.py..."
cat > openclaw/gateway.py << 'PYEOF'
import asyncio
import json
import os
import websockets
from openclaw.config import create_router
from openclaw.squirrel import SquirrelAgent
from openclaw.router import AuthError, RateLimitError

class OpenClawGateway:
    def __init__(self, host="0.0.0.0", port=18888):
        self.host = host
        self.port = port
        self.router = create_router()
        self.squirrel = SquirrelAgent(
            backend=os.getenv("SQUIRREL_BACKEND", "ollama"),
            base_url=os.getenv("SQUIRREL_URL", "http://localhost:11434"),
            model=os.getenv("SQUIRREL_MODEL", "deepseek-r1:8b"),
        )
        self.clients = {}
        self.server = None

    async def start(self):
        self.server = await websockets.serve(self._handle, self.host, self.port)
        print("OpenClaw Gateway running on ws://" + self.host + ":" + str(self.port))
        print("Registered platforms: " + str(self.router.list_platforms()))
        await asyncio.Future()

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        await self.router.close()
        print("Gateway stopped.")

    async def _handle(self, ws, path):
        self.clients[ws] = {"history": [], "platform": None}
        try:
            async for message in ws:
                await self._route(ws, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if ws in self.clients:
                del self.clients[ws]

    async def _route(self, ws, text):
        ctx = self.clients[ws]
        prefix, content = self._parse_prefix(text)
        await ws.send(json.dumps({"type": "received", "prefix": prefix}))
        try:
            if prefix in ("oc:", ""):
                await self._handle_local(ws, content, ctx)
            elif prefix == "all:":
                await self._handle_all(ws, content, ctx)
            else:
                await self._handle_platform(ws, prefix, content, ctx)
        except AuthError as e:
            await ws.send(json.dumps({"type": "error", "code": "AUTH", "message": str(e)}))
        except RateLimitError as e:
            await ws.send(json.dumps({"type": "error", "code": "RATE_LIMIT", "message": str(e)}))
        except ValueError as e:
            await ws.send(json.dumps({"type": "error", "code": "UNKNOWN_PREFIX", "message": str(e)}))
        except Exception as e:
            await ws.send(json.dumps({"type": "error", "code": "INTERNAL", "message": str(e)}))

    def _parse_prefix(self, text):
        text = text.strip()
        all_prefixes = ["hm:", "gpt:", "all:", "oc:"]
        all_prefixes.extend(self.router.list_platforms())
        for p in all_prefixes:
            if text.lower().startswith(p):
                return p, text[len(p):].strip()
        return "", text

    async def _handle_local(self, ws, content, ctx):
        await ws.send(json.dumps({"type": "start", "platform": "OpenClaw"}))
        full = []
        async for token in self.squirrel.chat_stream(content, ctx):
            await ws.send(json.dumps({"type": "token", "platform": "OpenClaw", "data": token}))
            full.append(token)
        response = "".join(full)
        self._update_history(ctx, content, response, "OpenClaw")
        await ws.send(json.dumps({"type": "done", "platform": "OpenClaw"}))

    async def _handle_platform(self, ws, prefix, content, ctx):
        cfg = self.router.platforms.get(prefix)
        platform_name = cfg.name if cfg else prefix
        await ws.send(json.dumps({"type": "start", "platform": platform_name}))
        messages = ctx.get("history", []) + [{"role": "user", "content": content}]
        full = []
        async for name, token in self.router.chat(prefix, messages):
            await ws.send(json.dumps({"type": "token", "platform": name, "data": token}))
            full.append(token)
        response = "".join(full)
        self._update_history(ctx, content, response, platform_name)
        await ws.send(json.dumps({"type": "done", "platform": platform_name}))

    async def _handle_all(self, ws, content, ctx):
        await ws.send(json.dumps({"type": "start_all"}))
        messages = ctx.get("history", []) + [{"role": "user", "content": content}]
        results = {}
        async for platform, token in self.router.chat("all:", messages):
            if platform not in results:
                results[platform] = []
                await ws.send(json.dumps({"type": "platform_start", "platform": platform}))
            results[platform].append(token)
            await ws.send(json.dumps({"type": "token", "platform": platform, "data": token}))
        for platform, tokens in results.items():
            response = "".join(tokens)
            self._update_history(ctx, content, response, platform)
        await ws.send(json.dumps({"type": "done_all"}))

    def _update_history(self, ctx, user_msg, assistant_msg, platform):
        if "history" not in ctx:
            ctx["history"] = []
        ctx["history"].append({"role": "user", "content": user_msg})
        if platform == "OpenClaw":
            ctx["history"].append({"role": "assistant", "content": assistant_msg})
        else:
            ctx["history"].append({"role": "assistant", "content": "[" + platform + "] " + assistant_msg})
        if len(ctx["history"]) > 20:
            ctx["history"] = ctx["history"][-20:]

if __name__ == "__main__":
    gateway = OpenClawGateway(
        host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
        port=int(os.getenv("GATEWAY_PORT", "18888"))
    )
    try:
        asyncio.run(gateway.start())
    except KeyboardInterrupt:
        asyncio.run(gateway.stop())
PYEOF

echo "[6/12] Creating requirements.txt..."
cat > requirements.txt << 'TXTEOF'
aiohttp>=3.9.0
websockets>=12.0
python-dotenv>=1.0.0
TXTEOF

echo "[7/12] Creating Dockerfile..."
cat > Dockerfile << 'TXTEOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY openclaw/ ./openclaw/
ENV PYTHONUNBUFFERED=1
ENV GATEWAY_HOST=0.0.0.0
ENV GATEWAY_PORT=18888
EXPOSE 18888
CMD ["python", "-m", "openclaw.gateway"]
TXTEOF

echo "[8/12] Creating docker-compose.yml..."
cat > docker-compose.yml << 'TXTEOF'
version: "3.8"

services:
  openclaw-gateway:
    build: .
    container_name: openclaw-gateway
    ports:
      - "18888:18888"
    env_file:
      - .env
    environment:
      - GATEWAY_HOST=0.0.0.0
      - GATEWAY_PORT=18888
    restart: unless-stopped
    networks:
      - openclaw-net
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; s=socket.socket(); s.connect(('localhost', 18888)); s.close()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama-models:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0:11434
    restart: unless-stopped
    networks:
      - openclaw-net

volumes:
  ollama-models:

networks:
  openclaw-net:
    driver: bridge
TXTEOF

echo "[9/12] Creating .env.example..."
cat > .env.example << 'TXTEOF'
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=18888
SQUIRREL_BACKEND=ollama
SQUIRREL_URL=http://localhost:11434
SQUIRREL_MODEL=deepseek-r1:8b
SENSENOVA_API_KEY=sk-xxx
CHERRY_BASE_URL=https://api.openai.com/v1
CHERRY_API_KEY=sk-xxx
CHERRY_MODEL=gpt-4o
TXTEOF

echo "[10/12] Creating restart.sh..."
cat > restart.sh << 'TXTEOF'
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
TXTEOF
chmod +x restart.sh

echo "[11/12] Creating reload.sh..."
cat > reload.sh << 'TXTEOF'
#!/bin/bash
set -e
echo "=== OpenClaw Gateway Hot Reload ==="
source .env
docker-compose restart
sleep 3
docker-compose ps
echo "=== Gateway reloaded ==="
TXTEOF
chmod +x reload.sh

echo "[12/12] Creating add_platform.sh..."
cat > add_platform.sh << 'TXTEOF'
#!/bin/bash
set -e
PREFIX=$1
NAME=$2
BASE_URL=$3
MODEL=$4
ENV_KEY=$5
if [ -z "$PREFIX" ] || [ -z "$NAME" ] || [ -z "$BASE_URL" ] || [ -z "$MODEL" ]; then
    echo "Usage: ./add_platform.sh <prefix> <name> <base_url> <model> [env_key]"
    exit 1
fi
ENV_KEY=${ENV_KEY:-"${NAME^^}_API_KEY"}
cat >> .env << ENV
# === ${NAME} (${PREFIX}) ===
${ENV_KEY}=your-api-key-here
ENV
sed -i "/return router/i\\    # ${PREFIX} ${NAME}\\n    router.register(\\\"${PREFIX}\\\", PlatformConfig(\\n        name=\\\"${NAME}\\\",\\n        base_url=\\\"${BASE_URL}\\\",\\n        api_key=os.getenv(\\\"${ENV_KEY}\\\", \\\"\\\"),\\n        model=\\\"${MODEL}\\\",\\n    ))\\n" openclaw/config.py
echo "Platform '${NAME}' (${PREFIX}) added!"
echo "1. Set ${ENV_KEY} in .env"
echo "2. Run ./restart.sh to apply"
TXTEOF
chmod +x add_platform.sh

echo ""
echo "=== 安装完成 ==="
echo "目录: ${PROJECT_DIR}"
echo ""
echo "下一步:"
echo "1. cd ${PROJECT_DIR}"
echo "2. cp .env.example .env"
echo "3. 编辑 .env 填入你的 API Key"
echo "4. docker-compose up -d"
echo ""
echo "新增平台: ./add_platform.sh <prefix> <name> <base_url> <model>"
echo "重启: ./restart.sh"
