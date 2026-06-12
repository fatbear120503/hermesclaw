import asyncio
import httpx
import time
import json
from typing import Dict, Any, Optional, List
from .config import settings, AGENTS_CONFIG
from ..models.message import MessageRequest, MessageResponse


def _serialize_request(request: MessageRequest) -> dict:
    """Serialize request to JSON-compatible dict."""
    return request.model_dump(mode='json')


def _build_openai_messages(content: str) -> List[Dict[str, str]]:
    """Build OpenAI chat messages format."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": content}
    ]


class APIDialogAdapter:
    """适配外部 API（OpenAI 格式）"""
    
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
    
    async def chat(self, content: str, timeout: int = 30, retries: int = 1) -> str:
        """发送消息到外部 API 并返回回复（支持重试）"""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": _build_openai_messages(content),
            "temperature": 0.7,
            "max_tokens": 2000,
        }
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            last_error = None
            for attempt in range(retries + 1):
                try:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    return data['choices'][0]['message']['content']
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                    last_error = e
                    if attempt < retries:
                        await asyncio.sleep(0.5 * (attempt + 1))  # 指数退避
                    continue
                except httpx.HTTPStatusError:
                    raise  # HTTP 错误不重试
            raise last_error if last_error else httpx.ConnectError("Max retries exceeded")


class MessageDispatcher:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT)
        self.start_time = time.time()
        self.total_requests = 0
        self.error_count = 0
        self.agent_status = {}
    
    async def initialize(self):
        await self._check_agents()
    
    async def shutdown(self):
        await self.client.aclose()
    
    async def _check_agents(self):
        """Check all agents status"""
        # Check local service agents
        for name, config in AGENTS_CONFIG.items():
            if config.mode == "service" and config.enabled:
                try:
                    resp = await self.client.get(f"{config.endpoint}/health", timeout=5)
                    self.agent_status[name] = {
                        "status": "online" if resp.status_code == 200 else "offline",
                        "mode": "service",
                        "endpoint": config.endpoint
                    }
                except Exception:
                    self.agent_status[name] = {
                        "status": "offline",
                        "mode": "service",
                        "endpoint": config.endpoint
                    }
            elif config.mode == "api":
                # API agents: check by sending a small request or assume online
                self.agent_status[name] = {
                    "status": "online",
                    "mode": "api",
                    "endpoint": config.base_url,
                    "model": config.model
                }
        
        # Check OpenClaw
        try:
            resp = await self.client.get(f"{settings.OPENCLAW_GATEWAY}/health", timeout=5)
            self.agent_status["openclaw"] = {
                "status": "online" if resp.status_code == 200 else "offline",
                "mode": "service",
                "endpoint": settings.OPENCLAW_GATEWAY
            }
        except Exception:
            self.agent_status["openclaw"] = {
                "status": "offline",
                "mode": "service",
                "endpoint": settings.OPENCLAW_GATEWAY
            }
    
    async def dispatch(self, request: MessageRequest) -> MessageResponse:
        self.total_requests += 1
        
        target = request.target_agent or request.prefix
        
        if target in ("none", "oc"):
            return await self._forward_to_openclaw(request)
        
        # Check aggregate groups
        if target in settings.AGGREGATE_GROUPS:
            return await self._dispatch_aggregate(request, target)
        
        # Single agent
        if target not in AGENTS_CONFIG:
            return MessageResponse(
                message_id=request.message_id,
                content=f"❌ 未知 Agent: {target}",
                agent=target,
                status="error"
            )
        
        config = AGENTS_CONFIG[target]
        if not config.enabled:
            return MessageResponse(
                message_id=request.message_id,
                content=f"⚠️ Agent '{target}' 已禁用",
                agent=target,
                status="error"
            )
        
        # Route based on mode
        if config.mode == "api":
            return await self._call_api_agent(request, config)
        else:
            return await self._call_service_agent(request, config, target)
    
    async def _call_api_agent(self, request: MessageRequest, config) -> MessageResponse:
        """调用外部 API Agent（Cherry, WorkBuddy）"""
        try:
            adapter = APIDialogAdapter(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model
            )
            content = await adapter.chat(request.content, timeout=settings.REQUEST_TIMEOUT)
            return MessageResponse(
                message_id=request.message_id,
                content=content,
                agent=request.target_agent or request.prefix,
                status="success"
            )
        except httpx.HTTPStatusError as e:
            self.error_count += 1
            status_code = e.response.status_code if hasattr(e, 'response') else '???'
            return MessageResponse(
                message_id=request.message_id,
                content=f"API 调用失败 (HTTP {status_code}): {str(e)}",
                agent=request.target_agent or request.prefix,
                status="error"
            )
        except Exception as e:
            self.error_count += 1
            return MessageResponse(
                message_id=request.message_id,
                content=f"API 调用失败: {str(e)}",
                agent=request.target_agent or request.prefix,
                status="error"
            )
    
    async def _call_service_agent(self, request: MessageRequest, config, agent_key: str) -> MessageResponse:
        """调用本地 Service Agent（Hermes, GPT）"""
        try:
            response = await self.client.post(
                f"{config.endpoint}/process",
                json=_serialize_request(request)
            )
            response.raise_for_status()
            data = response.json()
            return MessageResponse(
                message_id=request.message_id,
                content=data.get("content", ""),
                agent=agent_key,
                status="success"
            )
        except httpx.HTTPStatusError as e:
            self.error_count += 1
            status_code = e.response.status_code if hasattr(e, 'response') else '???'
            return MessageResponse(
                message_id=request.message_id,
                content=f"Service 调用失败 (HTTP {status_code}): {str(e)}",
                agent=agent_key,
                status="error"
            )
        except Exception as e:
            self.error_count += 1
            return MessageResponse(
                message_id=request.message_id,
                content=f"Service 调用失败: {str(e)}",
                agent=agent_key,
                status="error"
            )
    
    async def _call_single_agent(self, request: MessageRequest, agent_key: str) -> MessageResponse:
        """Internal: call any single agent by key."""
        if agent_key == "openclaw":
            return await self._forward_to_openclaw(request)
        
        if agent_key not in AGENTS_CONFIG:
            return MessageResponse(
                message_id=request.message_id,
                content=f"Agent not found: {agent_key}",
                agent=agent_key,
                status="error"
            )
        
        config = AGENTS_CONFIG[agent_key]
        if not config.enabled:
            return MessageResponse(
                message_id=request.message_id,
                content=f"⚠️ Agent '{agent_key}' 已禁用",
                agent=agent_key,
                status="error"
            )
        if config.mode == "api":
            return await self._call_api_agent(request, config)
        else:
            return await self._call_service_agent(request, config, agent_key)
    
    async def _dispatch_aggregate(self, request: MessageRequest, group_key: str) -> MessageResponse:
        """聚合调用多个 Agent（快速首响应 + 2秒补偿等待）"""
        agent_keys = settings.AGGREGATE_GROUPS.get(group_key, [])
        
        # 过滤已禁用的 agent
        enabled_keys = [k for k in agent_keys if k in AGENTS_CONFIG and AGENTS_CONFIG[k].enabled]
        
        if not enabled_keys:
            return MessageResponse(
                message_id=request.message_id,
                content=f"⚠️ 聚合组 '{group_key}' 没有可用的 Agent",
                agent=group_key,
                status="error"
            )
        
        # 启动并发调用
        tasks = {key: asyncio.create_task(self._call_single_agent(request, key)) for key in enabled_keys}
        results = {}
        aggregated_parts = []
        first_response_time = None
        COMPENSATION_WAIT = 2.0  # 收到第一个响应后最多再等 2 秒
        
        for completed in asyncio.as_completed(tasks.values()):
            try:
                resp = await completed
                # 确定是哪个 agent 完成的
                agent_key = None
                for k, t in tasks.items():
                    if t == completed:
                        agent_key = k
                        break
                
                if agent_key:
                    results[agent_key] = {"status": resp.status, "content": resp.content}
                    label = self._get_agent_label(agent_key)
                    
                    if resp.status == "success":
                        aggregated_parts.append(f"{label}\n{resp.content}")
                    else:
                        aggregated_parts.append(f"{label}\n⚠️ 回复失败: {resp.content}")
                
                # 记录首次响应时间
                if first_response_time is None:
                    first_response_time = time.time()
                    # 设置补偿等待超时
                    remaining = [t for k, t in tasks.items() if k not in results]
                    if remaining:
                        try:
                            await asyncio.wait_for(
                                asyncio.gather(*remaining, return_exceptions=True),
                                timeout=COMPENSATION_WAIT
                            )
                            # 收集剩余结果
                            for k, t in tasks.items():
                                if k not in results and t.done():
                                    try:
                                        r = t.result()
                                        results[k] = {"status": r.status, "content": r.content}
                                    except Exception as e:
                                        results[k] = {"status": "error", "content": str(e)}
                                        self.error_count += 1
                        except asyncio.TimeoutError:
                            # 补偿时间到，标记剩余为超时
                            for k, t in tasks.items():
                                if k not in results:
                                    results[k] = {"status": "timeout", "content": "响应较慢，稍后查看"}
                            break
                    else:
                        break  # 全部完成
                else:
                    # 在补偿窗口内完成的
                    pass
                    
            except Exception as e:
                self.error_count += 1
                # 找到对应 agent
                for k, t in tasks.items():
                    if t == completed and k not in results:
                        results[k] = {"status": "error", "content": str(e)}
        
        # 确保所有 agent 都有结果记录
        for key in enabled_keys:
            if key not in results:
                results[key] = {"status": "timeout", "content": "响应超时"}
        
        # 按原始顺序构建输出
        ordered_parts = []
        for key in enabled_keys:
            result = results.get(key, {})
            label = self._get_agent_label(key)
            if result.get("status") == "success":
                ordered_parts.append(f"{label}\n{result['content']}")
            elif result.get("status") == "timeout":
                ordered_parts.append(f"{label}\n⏳ 响应稍慢...")
            else:
                ordered_parts.append(f"{label}\n⚠️ 回复失败: {result.get('content', 'Unknown error')}")
        
        aggregated_content = "\n\n---\n\n".join(ordered_parts)
        
        return MessageResponse(
            message_id=request.message_id,
            content=aggregated_content,
            agent=group_key,
            status="success",
            metadata={"aggregated": True, "results": results}
        )
    
    def _get_agent_label(self, agent_key: str) -> str:
        labels = {
            "openclaw": "🐿️ 小松鼠 (OpenClaw)",
            "hm": "🦀 Hermes (SenseNova)",
            "gpt": "☁️ GPT",
            "cherry": "🍒 Cherry (Agnes AI)",
            "wb": "🤝 WorkBuddy (SiliconFlow)",
        }
        return labels.get(agent_key, agent_key)
    
    async def _forward_to_openclaw(self, request: MessageRequest) -> MessageResponse:
        try:
            response = await self.client.post(
                f"{settings.OPENCLAW_GATEWAY}/process",
                json=_serialize_request(request)
            )
            response.raise_for_status()
            data = response.json()
            return MessageResponse(
                message_id=request.message_id,
                content=data.get("content", ""),
                agent="openclaw",
                status="success"
            )
        except Exception as e:
            self.error_count += 1
            return MessageResponse(
                message_id=request.message_id,
                content=f"OpenClaw 转发失败: {str(e)}",
                agent="openclaw",
                status="error"
            )
    
    async def get_status(self) -> Dict[str, Any]:
        await self._check_agents()
        uptime = time.time() - self.start_time
        error_rate = self.error_count / max(self.total_requests, 1)
        
        return {
            "status": "running",
            "uptime": uptime,
            "agents": self.agent_status,
            "total_requests": self.total_requests,
            "error_rate": round(error_rate, 4),
            "aggregate_groups": settings.AGGREGATE_GROUPS
        }
