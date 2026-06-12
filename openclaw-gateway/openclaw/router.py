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
