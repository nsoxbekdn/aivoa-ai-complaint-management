"""Node 1 — normalise and size-check the incoming text before any token is spent."""

from __future__ import annotations

import re

from app.config import get_settings
from app.graph.state import GraphState

_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def prepare_input(state: GraphState) -> dict:
    """Collapse noise from PDF extraction and enforce the input size limit."""
    settings = get_settings()
    text = state.get("raw_text", "") or ""
    text = _BLANK_LINES.sub("\n\n", _WHITESPACE.sub(" ", text)).strip()

    warnings: list[str] = []
    if len(text) > settings.max_input_chars:
        text = text[: settings.max_input_chars]
        warnings.append(
            f"Input was longer than {settings.max_input_chars} characters and was truncated. "
            "Only the first part was analysed."
        )

    return {"raw_text": text, "warnings": warnings}
