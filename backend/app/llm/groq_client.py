"""The only module in the project that talks to Groq.

Keeping the vendor SDK behind one thin function means:
  * the API key never leaves the backend,
  * every graph node gets the same timeout / retry / fallback behaviour,
  * swapping the model (or the vendor) is a one-file change,
  * tests can monkeypatch a single symbol.

Output shaping is tiered, strongest first:
  1. ``json_schema``  — structured output bound to the caller's Pydantic model;
  2. ``json_object``  — "reply with a JSON object";
  3. plain text       — the prompt already names every key.
A model that rejects a tier is downgraded once per process (``_MODE_CACHE``), and whatever comes
back is still run through ``parse_json_object`` and Pydantic. The tier only reduces how often
the model gets the shape wrong; it is never the thing that guarantees it.
"""

from __future__ import annotations

import base64
import logging
from functools import lru_cache
from typing import Any

from groq import APIError, Groq
from pydantic import BaseModel

from app.config import get_settings
from app.llm.json_utils import JsonParseError, parse_json_object

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Any failure while talking to the LLM provider, safe to show to the client."""


class LLMNotConfiguredError(LLMError):
    """No API key present. Distinct from a network/provider failure."""


class LLMOutputError(LLMError):
    """The provider answered, but the answer was not usable JSON.

    Deliberately separate from a provider failure: switching to the fallback *model* is the
    wrong response to a shape problem. The graph's repair node handles this instead.
    """

    def __init__(self, message: str, raw_output: str = "") -> None:
        super().__init__(message)
        self.raw_output = raw_output


# (model id, whether a schema was sent) -> the best response mode that combination has
# actually been accepted with this process.
#
# The schema flag is part of the key on purpose. A schema-less call can only ever reach
# json_object or text, so caching its outcome under the bare model id would tell later
# *schema* calls that this model no longer accepts structured output — silently demoting
# every extraction and intake turn for the rest of the process.
_MODE_CACHE: dict[tuple[str, bool], str] = {}
_MODE_ORDER = ("json_schema", "json_object", "text")


@lru_cache
def _client() -> Groq:
    settings = get_settings()
    if not settings.llm_configured:
        raise LLMNotConfiguredError(
            "GROQ_API_KEY is not set. Add it to backend/.env to enable AI analysis."
        )
    return Groq(
        api_key=settings.groq_api_key,
        timeout=settings.groq_timeout_seconds,
        # Pinned rather than left to the SDK default (two), so the primary/fallback-model
        # policy does not change under us in a future SDK release. Four because a burst of
        # concurrent analyses on a free-tier key answers 429 for a second or two; the SDK's
        # exponential backoff rides that out, whereas giving up early surfaces to the user
        # as "the AI is unavailable" on a request that would have succeeded.
        max_retries=4,
    )


def _inline_refs(node: Any, defs: dict) -> Any:
    """Replace every `$ref` with the definition it points at.

    Strict structured output rejects a `$ref`/`null` union it cannot disambiguate, so the
    enum definitions have to be inlined before the union is flattened.
    """
    if isinstance(node, list):
        return [_inline_refs(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        target = dict(defs.get(ref.rsplit("/", 1)[1], {}))
        target.update({key: value for key, value in node.items() if key != "$ref"})
        return _inline_refs(target, defs)
    return {key: _inline_refs(value, defs) for key, value in node.items()}


def _flatten_nullable(node: dict) -> None:
    """`anyOf: [X, null]` -> a single nullable node.

    Pydantic writes every `X | None` field as a two-branch union. Providers require the
    branches to be distinguishable, so an optional enum is rejected outright. Collapsing the
    union into `{"type": ["string", "null"], "enum": [...]}` keeps the same meaning and is
    accepted.
    """
    branches = node.get("anyOf")
    if not isinstance(branches, list) or len(branches) != 2:
        return
    nulls = [b for b in branches if isinstance(b, dict) and b.get("type") == "null"]
    others = [b for b in branches if isinstance(b, dict) and b.get("type") != "null"]
    if len(nulls) != 1 or len(others) != 1:
        return

    value = others[0]
    node.pop("anyOf")
    node.update(value)
    value_type = value.get("type", "string")
    node["type"] = [value_type, "null"] if isinstance(value_type, str) else [*value_type, "null"]
    if "enum" in node and None not in node["enum"]:
        node["enum"] = [*node["enum"], None]


def _strictify(node: Any) -> None:
    """Make a JSON Schema acceptable to strict structured-output implementations.

    Every object must list all of its properties as required and forbid extras, the optional
    unions must be flattened, and the annotation keywords Pydantic adds for humans are not
    part of the contract.
    """
    if isinstance(node, list):
        for item in node:
            _strictify(item)
        return
    if not isinstance(node, dict):
        return

    # Flatten first: merging a union pulls the branch's own annotations up into this node.
    _flatten_nullable(node)
    for keyword in ("default", "title", "format", "examples", "$defs"):
        node.pop(keyword, None)

    if node.get("type") == "object" or "properties" in node:
        properties = node.get("properties", {})
        node["additionalProperties"] = False
        node["required"] = list(properties)

    for value in node.values():
        _strictify(value)


def strict_json_schema(model_cls: type[BaseModel]) -> dict:
    """Pydantic model -> a strict JSON Schema payload for `response_format`."""
    schema = model_cls.model_json_schema()
    schema = _inline_refs(schema, schema.get("$defs", {}))
    _strictify(schema)
    return {
        "type": "json_schema",
        "json_schema": {"name": model_cls.__name__, "strict": True, "schema": schema},
    }


def _rejects_response_format(exc: Exception) -> bool:
    """True when the failure looks like "this model will not accept that response_format".

    Providers word this differently per model, so any bad request — or any error naming the
    parameter — is treated as a reason to try a weaker mode. Auth, rate-limit, timeout and
    server errors are not bad requests and must not be swallowed here.
    """
    text = str(exc).lower()
    if any(token in text for token in ("response_format", "json_object", "json_schema", "json mode")):
        return True
    return "badrequest" in type(exc).__name__.lower() or getattr(exc, "status_code", None) == 400


def _reasoning_kwargs() -> dict[str, str]:
    """Cap how much of the token budget a reasoning model may spend thinking.

    Without this, gpt-oss spends most of ``max_completion_tokens`` on its private chain of
    thought and returns a truncated or empty answer — which surfaces as "the AI returned
    output that could not be read as JSON", not as the budget problem it actually is.
    """
    effort = get_settings().groq_reasoning_effort.strip()
    return {"reasoning_effort": effort} if effort else {}


def _response_format(mode: str, schema: type[BaseModel] | None) -> dict | None:
    if mode == "json_schema" and schema is not None:
        return strict_json_schema(schema)
    if mode == "json_object":
        return {"type": "json_object"}
    return None


def _response_content(response: Any, model: str) -> str:
    """Read one non-empty assistant message from an SDK response.

    Groq 1.x returns typed Pydantic response objects, but a provider-side empty ``choices``
    array or ``content=None`` is still possible. Treat that as unusable model output rather
    than leaking ``IndexError``/``AttributeError`` or returning an empty successful result.
    """
    choices = getattr(response, "choices", None)
    if not choices:
        raise LLMOutputError(f"{model} returned no completion choices.")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if not isinstance(content, str) or not content.strip():
        raise LLMOutputError(f"{model} returned an empty completion.")
    return content


def _call(
    model: str, system_prompt: str, user_prompt: str, max_tokens: int, schema: type[BaseModel] | None
) -> str:
    settings = get_settings()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    cache_key = (model, schema is not None)
    start = _MODE_ORDER.index(_MODE_CACHE.get(cache_key, "json_schema" if schema else "json_object"))
    modes = [mode for mode in _MODE_ORDER[start:] if mode != "json_schema" or schema is not None]

    last_exc: Exception | None = None
    for mode in modes:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": settings.groq_temperature,
            "max_completion_tokens": max_tokens,
            **_reasoning_kwargs(),
        }
        response_format = _response_format(mode, schema)
        if response_format is not None:
            kwargs["response_format"] = response_format

        try:
            response = _client().chat.completions.create(**kwargs)
        except APIError as exc:
            if not _rejects_response_format(exc):
                raise
            logger.info("Model %s rejected %s mode; trying a weaker response mode.", model, mode)
            last_exc = exc
            continue

        _MODE_CACHE[cache_key] = mode
        return _response_content(response, model)

    raise last_exc if last_exc else LLMError(f"{model}: no usable response mode.")


def complete_json(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 1200,
    schema: type[BaseModel] | None = None,
) -> dict:
    """Ask the LLM for a JSON object and return it parsed.

    `schema` (optional) is the Pydantic model the answer will be validated against; when given
    it is also sent as a structured-output schema.

    Failure modes are kept apart on purpose:
      * provider/model failure (auth, rate limit, timeout, model gone) -> try the fallback model;
      * unusable output -> raise LLMOutputError immediately, so the graph's repair node deals
        with it. Swapping models is not a fix for a malformed reply, and Pydantic validation
        errors (raised by the caller, not here) never reach this function at all.
    """
    settings = get_settings()
    models = [settings.groq_model]
    if settings.groq_fallback_model and settings.groq_fallback_model != settings.groq_model:
        models.append(settings.groq_fallback_model)

    last_error: str = "unknown error"
    for model in models:
        try:
            raw = _call(model, system_prompt, user_prompt, max_tokens, schema)
        except LLMNotConfiguredError:
            raise
        except LLMOutputError:
            raise
        except APIError as exc:
            # str(exc) can carry a request id and status, never the key (the SDK redacts it).
            last_error = f"{model}: {type(exc).__name__}"
            logger.warning("Groq call failed on model %s: %s", model, type(exc).__name__)
            continue

        try:
            return parse_json_object(raw)
        except JsonParseError as exc:
            logger.warning("Groq model %s returned output that is not JSON.", model)
            raise LLMOutputError(
                "The AI returned output that could not be read as JSON.", raw_output=raw
            ) from exc

    raise LLMError(f"AI provider unavailable ({last_error}).")


def complete_text(
    system_prompt: str, user_prompt: str, *, max_tokens: int = 500, model: str | None = None
) -> str:
    """Plain-text completion, used by the grounded complaint chat.

    `model` pins the call to one model instead of walking the usual primary-then-fallback list.
    Reply phrasing uses it so a cosmetic call cannot spend the main model's token budget.
    """
    settings = get_settings()
    for model in [model] if model else [settings.groq_model, settings.groq_fallback_model]:
        if not model:
            continue
        try:
            response = _client().chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=settings.groq_temperature,
                max_completion_tokens=max_tokens,
                **_reasoning_kwargs(),
            )
            return _response_content(response, model).strip()
        except LLMNotConfiguredError:
            raise
        except LLMOutputError:
            raise
        except APIError:
            logger.warning("Groq text call failed on model %s.", model)
    raise LLMError("AI provider unavailable.")


def complete_vision_json(
    prompt: str,
    images: list[bytes],
    *,
    media_type: str = "image/jpeg",
    max_tokens: int = 4000,
) -> dict:
    """Transcribe one or more page images with the configured Groq vision model.

    Qwen vision supports JSON Object mode but not the strict schema tier used by the text
    workflow. Its result is still parsed here and validated by the caller's Pydantic model.
    """
    settings = get_settings()
    if not settings.groq_vision_model:
        raise LLMNotConfiguredError("GROQ_VISION_MODEL is not configured.")

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for image in images:
        encoded = base64.b64encode(image).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{encoded}"},
            }
        )

    common: dict[str, Any] = {
        "model": settings.groq_vision_model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_completion_tokens": max_tokens,
        # Qwen otherwise spends the output budget on a visible <think> trace.
        "reasoning_effort": "none",
    }

    last_error: Exception | None = None
    for response_format in ({"type": "json_object"}, None):
        kwargs = dict(common)
        if response_format is not None:
            kwargs["response_format"] = response_format
        try:
            response = _client().chat.completions.create(**kwargs)
            raw = _response_content(response, settings.groq_vision_model)
            return parse_json_object(raw)
        except JsonParseError as exc:
            raise LLMOutputError(
                "Groq Vision returned OCR output that was not valid JSON.", raw_output=raw
            ) from exc
        except LLMOutputError:
            raise
        except APIError as exc:
            last_error = exc
            if response_format is not None and _rejects_response_format(exc):
                logger.info("Vision model rejected JSON mode; retrying without response_format.")
                continue
            break

    logger.warning(
        "Groq vision call failed on model %s: %s",
        settings.groq_vision_model,
        type(last_error).__name__ if last_error else "UnknownError",
    )
    raise LLMError("Vision OCR is temporarily unavailable. Type the complaint or retry the file.")
