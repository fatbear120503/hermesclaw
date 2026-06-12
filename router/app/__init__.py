from fastapi import APIRouter
from .main import app

api_router = APIRouter()

# Include all routers
from .routers import health, route, status

app.include_router(health.router, prefix="/api/v1")
app.include_router(route.router, prefix="/api/v1")
app.include_router(status.router, prefix="/api/v1")
