from fastapi import APIRouter
from ..core.dispatcher import MessageDispatcher

router = APIRouter()
dispatcher = MessageDispatcher()

@router.get("/status")
async def status():
    return await dispatcher.get_status()
