import json
from typing import AsyncIterator
import aiohttp

class SquirrelAgent:
    def __init__(self, backend="ollama", base_url="http://localhost:11434", model="deepseek-r1:8b", api_key=""):
        self.backend = backend
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self._headers = {}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

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
        async with aiohttp.ClientSession(headers=self._headers) as s:
            async with s.post(self.base_url + "/v1/chat/completions", json=payload) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def _stream_http(self, messages):
        payload = {"model": self.model, "messages": messages, "stream": True}
        async with aiohttp.ClientSession(headers=self._headers) as s:
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
