"""FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import api_router
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()

app = FastAPI(
    title="AIVOA Complaint Management API",
    version="1.0.0",
    description=(
        "AI-assisted intake for pharmaceutical customer complaints. All AI output is "
        "preliminary decision support and requires human QA review."
    ),
)

# The browser calls this API from a different origin (Vite dev server), so CORS is explicit.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "AIVOA Complaint Management API", "docs": "/docs", "health": "/api/health"}
