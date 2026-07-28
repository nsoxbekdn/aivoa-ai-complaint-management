"""Application settings.

Every tunable value comes from the environment (or a local .env file) so that no secret
is ever hardcoded, and so the LLM model can be swapped without touching code.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute, so the server picks up backend/.env no matter which directory it was started from.
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # --- database -------------------------------------------------------------
    # Postgres is the target database. SQLite is accepted so the project can be
    # started with zero infrastructure (and so tests run offline).
    database_url: str = "sqlite:///./aivoa.db"

    # --- LLM ------------------------------------------------------------------
    groq_api_key: str = ""
    # Model IDs live here and in .env only — never inside a graph node, so swapping models is
    # an environment change. See the README note on why these are not gemma2-9b-it.
    groq_model: str = "openai/gpt-oss-120b"
    groq_fallback_model: str = "openai/gpt-oss-20b"
    # Vision is used only for OCR/document understanding. Keeping it separate makes hosted
    # model changes an environment edit rather than a code change.
    groq_vision_model: str = "qwen/qwen3.6-27b"
    # Wording the assistant's reply is the one job in this system that needs no reasoning and
    # no accuracy — every fact is handed to it. Pointing it at the small model keeps the large
    # model's daily token budget for extraction and classification, and it answers in ~0.5s.
    groq_reply_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: float = 45.0
    # Low temperature: extraction and classification must be reproducible, not creative.
    groq_temperature: float = 0.1
    # gpt-oss is a reasoning model: its private chain of thought is billed against
    # max_completion_tokens, so at the default effort a 900-token budget was measured
    # spending 831 tokens thinking and returning a truncated (sometimes empty) answer.
    # "low" cuts that to ~260 and leaves room for the JSON. Groq accepts only
    # low | medium | high here; blank the value for a model that has no reasoning mode.
    groq_reasoning_effort: str = "low"

    # --- API ------------------------------------------------------------------
    frontend_origin: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_upload_size_mb: int = 5
    max_ocr_pages: int = 3
    max_vision_payload_mb: int = 18
    vision_image_max_edge: int = 2048
    # Guard-rail against pasting a whole book into the textarea.
    max_input_chars: int = 40_000

    # --- workflow -------------------------------------------------------------
    max_extraction_retries: int = 1

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.groq_api_key)


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is parsed once per process."""
    return Settings()
