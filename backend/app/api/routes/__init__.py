from fastapi import APIRouter

from app.api.routes import complaints, health

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(complaints.router)

__all__ = ["api_router"]
