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
            api_key=os.getenv("SQUIRREL_API_KEY", ""),
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
        all_prefixes = ["hm:", "gpt:", "cherry:", "wb:", "all:", "oc:"]
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
