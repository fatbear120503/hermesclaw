from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal
import asyncio
import httpx
import time
import uuid

from .core.dispatcher import MessageDispatcher
from .core.config import settings
from .models.message import MessageRequest, MessageResponse, RouterStatus

app = FastAPI(
    title="HermesClaw Router",
    description="Multi-Agent Router for OpenClaw Plugin",
    version="0.1.0"
)

dispatcher = MessageDispatcher()

@app.on_event("startup")
async def startup_event():
    await dispatcher.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    await dispatcher.shutdown()

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0", "timestamp": time.time()}

@app.get("/status", response_model=RouterStatus)
async def get_status():
    return await dispatcher.get_status()

@app.post("/route", response_model=MessageResponse)
async def route_message(request: MessageRequest):
    try:
        response = await dispatcher.dispatch(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/route/{agent_type}")
async def route_to_agent(agent_type: str, request: MessageRequest):
    try:
        request.target_agent = agent_type
        response = await dispatcher.dispatch(request)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
