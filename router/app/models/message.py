import uuid
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal
from datetime import datetime

class MessageRequest(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    prefix: Literal["hm", "gpt", "cherry", "wb", "both", "all", "oc", "none"] = "none"
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    target_agent: Optional[str] = None

class MessageResponse(BaseModel):
    message_id: str
    content: str
    agent: str
    status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class RouterStatus(BaseModel):
    status: str
    uptime: float
    agents: Dict[str, Any]
    total_requests: int
    error_rate: float
