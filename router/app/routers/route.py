from fastapi import APIRouter, HTTPException
from ..models.message import MessageRequest, MessageResponse
from ..core.dispatcher import MessageDispatcher

router = APIRouter()
dispatcher = MessageDispatcher()

@router.post("/route", response_model=MessageResponse)
async def route_message(request: MessageRequest):
    try:
        return await dispatcher.dispatch(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
