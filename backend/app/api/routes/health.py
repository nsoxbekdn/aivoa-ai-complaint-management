"""Liveness endpoint — also reports whether the AI provider is configured."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # noqa: BLE001 - health must never raise
        database_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "database": "up" if database_ok else "down",
        "llm_configured": settings.llm_configured,
        "llm_model": settings.groq_model,
        "llm_fallback_model": settings.groq_fallback_model,
        "vision_model": settings.groq_vision_model,
    }
