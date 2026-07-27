"""Turn "almost JSON" model output into a real dict.

LLMs wrap JSON in ``` fences, prepend "Here is the JSON:", or leave a trailing comma.
These are cheap, deterministic fixes — worth trying before spending another API call.
"""

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


class JsonParseError(ValueError):
    """Raised when the text cannot be coerced into a JSON object."""


def _balanced_object(text: str) -> str | None:
    """Return the first top-level {...} block, respecting braces inside strings."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_json_object(raw: str) -> dict:
    """Best-effort JSON parse. Raises JsonParseError if nothing usable is found."""
    if not raw or not raw.strip():
        raise JsonParseError("empty model response")

    candidates: list[str] = []
    fenced = _FENCE.search(raw)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(raw)

    for candidate in candidates:
        block = _balanced_object(candidate) or candidate.strip()
        for attempt in (block, _TRAILING_COMMA.sub(r"\1", block)):
            try:
                parsed = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise JsonParseError("model response did not contain a JSON object")
