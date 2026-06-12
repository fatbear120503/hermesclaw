import asyncio
import json
import httpx
import os
import time
import uuid
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import websockets

app = FastAPI(title="HermesClaw WebSocket Adapter")

class ProcessRequest(BaseModel):
    content: str
    prefix: str = "none"
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    message_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class ProcessResponse(BaseModel):
    message_id: str
    content: str
    agent: str
    status: str

# Client registry
_clients: Dict[str, Any] = {}

class WebSocketAgentClient:
    """HTTP-to-WebSocket adapter for Hermes/OpenClaw agents."""
    
    def __init__(self, name: str, ws_uri: str, http_fallback: Optional[str] = None):
        self.name = name
        self.ws_uri = ws_uri
        self.http_fallback = http_fallback
        self.ws = None
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self._connected = False
        self._lock = asyncio.Lock()
    
    async def connect(self):
        """Establish WebSocket connection with handshake."""
        try:
            self.ws = await websockets.connect(self.ws_uri)
            
            # Wait for challenge
            challenge_msg = await asyncio.wait_for(self.ws.recv(), timeout=5)
            challenge_data = json.loads(challenge_msg)
            
            if challenge_data.get("event") == "connect.challenge":
                # Respond to challenge
                nonce = challenge_data["payload"]["nonce"]
                response = {
                    "type": "event",
                    "event": "connect.response",
                    "payload": {"nonce": nonce, "accepted": True}
                }
                await self.ws.send(json.dumps(response))
            
            self._connected = True
            
            # Start listener task
            asyncio.create_task(self._listen())
            return True
        except Exception as e:
            print(f"[{self.name}] WebSocket connect failed: {e}")
            return False
    
    async def _listen(self):
        """Background task to receive WebSocket messages."""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    
                    # Handle different message types
                    msg_type = data.get("type")
                    
                    if msg_type == "message":
                        # Check if this is a response to a pending request
                        msg_id = data.get("message_id") or data.get("id")
                        if msg_id and msg_id in self.pending_requests:
                            future = self.pending_requests.pop(msg_id)
                            future.set_result(data)
                    elif msg_type == "event":
                        # Handle events (ping, status, etc.)
                        event = data.get("event")
                        if event == "ping":
                            await self.ws.send(json.dumps({
                                "type": "event", "event": "pong"
                            }))
                except json.JSONDecodeError:
                    pass
        except websockets.exceptions.ConnectionClosed:
            self._connected = False
        except Exception as e:
            print(f"[{self.name}] Listener error: {e}")
            self._connected = False
    
    async def process(self, request: ProcessRequest) -> ProcessResponse:
        """Send message via WebSocket and wait for response."""
        msg_id = request.message_id or str(uuid.uuid4())
        
        # Ensure connection
        if not self._connected:
            async with self._lock:
                if not self._connected:
                    await self.connect()
        
        if not self._connected:
            # Fallback to HTTP if configured
            if self.http_fallback:
                return await self._http_fallback(request, msg_id)
            return ProcessResponse(
                message_id=msg_id,
                content=f"[{self.name}] WebSocket not connected",
                agent=self.name,
                status="error"
            )
        
        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[msg_id] = future
        
        # Send message
        ws_message = {
            "type": "message",
            "message_id": msg_id,
            "content": request.content,
            "user_id": request.user_id,
            "chat_id": request.chat_id,
            "metadata": request.metadata or {}
        }
        
        try:
            await self.ws.send(json.dumps(ws_message))
            
            # Wait for response (with timeout)
            response_data = await asyncio.wait_for(future, timeout=30)
            
            return ProcessResponse(
                message_id=msg_id,
                content=response_data.get("content", ""),
                agent=self.name,
                status="success"
            )
        except asyncio.TimeoutError:
            self.pending_requests.pop(msg_id, None)
            return ProcessResponse(
                message_id=msg_id,
                content=f"[{self.name}] Response timeout",
                agent=self.name,
                status="error"
            )
        except Exception as e:
            self.pending_requests.pop(msg_id, None)
            return ProcessResponse(
                message_id=msg_id,
                content=f"[{self.name}] Error: {str(e)}",
                agent=self.name,
                status="error"
            )
    
    async def _http_fallback(self, request: ProcessRequest, msg_id: str) -> ProcessResponse:
        """Fallback to HTTP if WebSocket fails."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.http_fallback}/process",
                    json=request.dict(),
                    timeout=30
                )
                data = response.json()
                return ProcessResponse(
                    message_id=msg_id,
                    content=data.get("content", ""),
                    agent=self.name,
                    status="success"
                )
        except Exception as e:
            return ProcessResponse(
                message_id=msg_id,
                content=f"[{self.name}] HTTP fallback failed: {str(e)}",
                agent=self.name,
                status="error"
            )
    
    async def disconnect(self):
        if self.ws:
            await self.ws.close()
            self._connected = False


class HTTPAgentClient:
    """HTTP client for standard OpenAI-compatible API agents."""
    
    def __init__(self, name: str, base_url: str, api_key: str, model: str):
        self.name = name
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )
    
    async def process(self, request: ProcessRequest) -> ProcessResponse:
        """Send message to OpenAI-compatible API and return response."""
        msg_id = request.message_id or str(uuid.uuid4())
        
        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": request.content}],
                "stream": False
            }
            
            response = await self._client.post(
                f"{self.base_url}/chat/completions",
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            content = data["choices"][0]["message"]["content"]
            
            return ProcessResponse(
                message_id=msg_id,
                content=content,
                agent=self.name,
                status="success"
            )
        except Exception as e:
            return ProcessResponse(
                message_id=msg_id,
                content=f"[{self.name}] API error: {str(e)}",
                agent=self.name,
                status="error"
            )
    
    async def health_check(self) -> bool:
        """Check if API is reachable by making a minimal request."""
        try:
            # Try a simple models list or just check connectivity
            response = await self._client.get(
                f"{self.base_url}/models",
                timeout=5.0
            )
            return response.status_code < 500
        except Exception:
            return False
    
    async def disconnect(self):
        await self._client.aclose()

@app.on_event("startup")
async def startup():
    # Hermes WebSocket client
    _clients["hm"] = WebSocketAgentClient(
        name="hm",
        ws_uri="ws://localhost:9119/ws",
        http_fallback=None
    )
    await _clients["hm"].connect()
    
    # OpenClaw WebSocket client
    _clients["openclaw"] = WebSocketAgentClient(
        name="openclaw",
        ws_uri="ws://localhost:18789/ws",
        http_fallback=None
    )
    await _clients["openclaw"].connect()
    
    # Cherry HTTP client (SenseNova)
    cherry_base = os.getenv("CHERRY_BASE_URL", "https://api.sensenova.cn/v1")
    cherry_key = os.getenv("CHERRY_API_KEY", "")
    cherry_model = os.getenv("CHERRY_MODEL", "sensenova-6.7-flash-lite")
    if cherry_key:
        _clients["cherry"] = HTTPAgentClient(
            name="cherry",
            base_url=cherry_base,
            api_key=cherry_key,
            model=cherry_model
        )
        print(f"[Adapter] Cherry client initialized: {cherry_model}")
    else:
        print("[Adapter] Cherry client skipped (missing API key)")
    
    # WorkBuddy HTTP client (OpenAI-compatible)
    wb_base = os.getenv("WorkBuddy_BASE_URL", "")
    wb_key = os.getenv("WorkBuddy_API_KEY", "")
    wb_model = os.getenv("WorkBuddy_MODEL", "Qwen/Qwen3-8B")
    if wb_base and wb_key:
        _clients["wb"] = HTTPAgentClient(
            name="wb",
            base_url=wb_base,
            api_key=wb_key,
            model=wb_model
        )
        print(f"[Adapter] WorkBuddy client initialized: {wb_model}")
    else:
        print("[Adapter] WorkBuddy client skipped (missing env vars)")

@app.on_event("shutdown")
async def shutdown():
    for client in _clients.values():
        await client.disconnect()

@app.get("/health")
async def health():
    status = {}
    for name, client in _clients.items():
        if isinstance(client, WebSocketAgentClient):
            status[name] = "connected" if client._connected else "disconnected"
        elif isinstance(client, HTTPAgentClient):
            status[name] = "available" if await client.health_check() else "unreachable"
    return {"status": "ok", "agents": status}

@app.post("/process")
async def process_message(request: ProcessRequest):
    """Process a single message (used by Router for single-agent routing)."""
    # Determine target from prefix or metadata
    target = request.prefix
    if target == "none" or target == "oc":
        target = "openclaw"
    
    if target not in _clients:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {target}")
    
    return await _clients[target].process(request)

@app.post("/process/both")
async def process_both(request: ProcessRequest):
    """Process message with both OpenClaw and Hermes (aggregate)."""
    msg_id = request.message_id or str(uuid.uuid4())
    
    # Send to both concurrently
    tasks = []
    for name in ["openclaw", "hm"]:
        if name in _clients:
            req_copy = ProcessRequest(
                content=request.content,
                prefix=name,
                user_id=request.user_id,
                chat_id=request.chat_id,
                message_id=msg_id,
                metadata=request.metadata
            )
            tasks.append(_clients[name].process(req_copy))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Build aggregated response
    parts = []
    for result in results:
        if isinstance(result, Exception):
            parts.append(f"⚠️ Error: {str(result)}")
        elif result.status == "success":
            label = "🐿️ 小松鼠 (OpenClaw)" if result.agent == "openclaw" else "🦀 Hermes"
            parts.append(f"【{label}】\n{result.content}")
        else:
            label = "🐿️ 小松鼠 (OpenClaw)" if result.agent == "openclaw" else "🦀 Hermes"
            parts.append(f"【{label}】\n⚠️ {result.content}")
    
    return ProcessResponse(
        message_id=msg_id,
        content="\n\n---\n\n".join(parts),
        agent="both",
        status="success"
    )

@app.post("/process/all")
async def process_all(request: ProcessRequest):
    """Process message with all available agents (aggregate)."""
    msg_id = request.message_id or str(uuid.uuid4())
    
    # Send to all available agents concurrently
    tasks = []
    agent_names = ["openclaw", "hm", "cherry", "wb"]
    for name in agent_names:
        if name in _clients:
            req_copy = ProcessRequest(
                content=request.content,
                prefix=name,
                user_id=request.user_id,
                chat_id=request.chat_id,
                message_id=msg_id,
                metadata=request.metadata
            )
            tasks.append(_clients[name].process(req_copy))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Build aggregated response
    parts = []
    for result in results:
        if isinstance(result, Exception):
            parts.append(f"⚠️ Error: {str(result)}")
        elif result.status == "success":
            label = _get_agent_label(result.agent)
            parts.append(f"【{label}】\n{result.content}")
        else:
            label = _get_agent_label(result.agent)
            parts.append(f"【{label}】\n⚠️ {result.content}")
    
    return ProcessResponse(
        message_id=msg_id,
        content="\n\n---\n\n".join(parts),
        agent="all",
        status="success"
    )

def _get_agent_label(agent_key: str) -> str:
    """Get human-readable label for an agent."""
    labels = {
        "openclaw": "🐿️ 小松鼠 (OpenClaw)",
        "hm": "🦀 Hermes (SenseNova)",
        "cherry": "🍒 Cherry (Agnes)",
        "wb": "🤝 WorkBuddy (Qwen)",
    }
    return labels.get(agent_key, agent_key)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18892)
