import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any, List, Optional

# Load .env file - try multiple locations
_env_loaded = False
for _env_path in [
    Path("~/.config/hermesclaw/.env"),
    Path.cwd() / "config" / ".env",
    Path.cwd() / ".env",
]:
    if _env_path.exists():
        load_dotenv(_env_path, override=True)
        _env_loaded = True
        break

class AgentConfig:
    """Agent 配置类（兼容 Pydantic）"""
    def __init__(self, name: str, mode: str = "service", endpoint: Optional[str] = None,
                 base_url: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, description: str = "", enabled: bool = True):
        self.name = name
        self.mode = mode
        self.endpoint = endpoint
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.description = description
        self.enabled = enabled

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HERMESCLAW_",
        extra="ignore"
    )
    
    APP_NAME: str = "HermesClaw Router"
    VERSION: str = "0.1.0"
    PORT: int = 18889
    HOST: str = "0.0.0.0"
    
    # OpenClaw Gateway
    OPENCLAW_GATEWAY: str = "http://localhost:18789"
    
    # Aggregate groups
    AGGREGATE_GROUPS: Dict[str, List[str]] = {
        "both": ["cherry", "wb"],
        "all": ["cherry", "wb"],
    }
    
    # Timeouts
    REQUEST_TIMEOUT: int = 15
    MAX_RETRIES: int = 3
    
    # Logging
    LOG_LEVEL: str = "INFO"

# Build settings
settings = Settings()

# Override AGGREGATE_GROUPS from env
if os.environ.get("HERMESCLAW_AGGREGATE_BOTH"):
    settings.AGGREGATE_GROUPS["both"] = [
        a.strip() for a in os.environ.get("HERMESCLAW_AGGREGATE_BOTH").split(",")
    ]
if os.environ.get("HERMESCLAW_AGGREGATE_ALL"):
    settings.AGGREGATE_GROUPS["all"] = [
        a.strip() for a in os.environ.get("HERMESCLAW_AGGREGATE_ALL").split(",")
    ]

# ==========================================
# Agent 配置
# ==========================================

AGENTS_CONFIG: Dict[str, AgentConfig] = {
    # 1. 本地服务 - Hermes
    "hm": AgentConfig(
        name="Hermes Agent",
        endpoint=os.environ.get("HERMESCLAW_AGENT_HM", "http://localhost:9119"),
        description="本地 AI 服务 (SenseNova 6.7 Flash-Lite)",
        mode="service",
    ),
    
    # 2. 本地服务 - GPT (预留)
    "gpt": AgentConfig(
        name="GPT Agent",
        endpoint=os.environ.get("HERMESCLAW_AGENT_GPT", "http://localhost:18890"),
        description="Cloud-based GPT agent",
        enabled=False,
        mode="service",
    ),
    
    # 3. 外部 API - Cherry (Agnes AI) — 临时禁用（API Key 无效）
    "cherry": AgentConfig(
        name="Cherry Agent",
        base_url=os.environ.get("CHERRY_BASE_URL", "https://apihub.agnes-ai.com/v1"),
        api_key=os.environ.get("CHERRY_API_KEY", ""),
        model=os.environ.get("CHERRY_MODEL", "agnes-2.0-flash"),
        description="Agnes AI agent (OpenAI-compatible)",
        mode="api",
        enabled=True,
    ),
    
    # 4. 外部 API - WorkBuddy (SiliconFlow)
    "wb": AgentConfig(
        name="WorkBuddy Agent",
        base_url=os.environ.get("WORKBUDDY_BASE_URL", "https://api.siliconflow.cn/v1"),
        api_key=os.environ.get("WORKBUDDY_API_KEY", ""),
        model=os.environ.get("WORKBUDDY_MODEL", "Qwen/Qwen3-8B"),
        description="SiliconFlow agent (Qwen3-8B)",
        mode="api",
    ),
}
