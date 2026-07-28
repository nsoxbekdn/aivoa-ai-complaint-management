"""Groq client behaviour: response-mode tiering, model fallback, and failure separation.

No network: a fake client object replaces `_client()`, so these tests assert exactly which
requests the code would send.
"""

from types import SimpleNamespace

import httpx
import pytest
from groq import APITimeoutError, BadRequestError, RateLimitError
from groq.types.chat.chat_completion import ChatCompletion

from app.llm import groq_client
from app.llm.groq_client import (
    LLMError,
    LLMOutputError,
    complete_json,
    complete_text,
    complete_vision_json,
    strict_json_schema,
)
from app.config import get_settings
from app.schemas.analysis import ExtractedComplaintFields


def _status_error(
    error_type: type[BadRequestError] | type[RateLimitError],
    status_code: int,
    message: str,
) -> BadRequestError | RateLimitError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return error_type(message, response=response, body={"error": {"message": message}})


def _bad_request(message: str) -> BadRequestError:
    return _status_error(BadRequestError, 400, message)


def _rate_limit(message: str = "rate limited") -> RateLimitError:
    return _status_error(RateLimitError, 429, message)


def _reply(content: str | None, *, choices: bool = True) -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-test",
            "choices": (
                [
                    {
                        "finish_reason": "stop",
                        "index": 0,
                        "message": {"content": content, "role": "assistant"},
                    }
                ]
                if choices
                else []
            ),
            "created": 0,
            "model": "test-model",
            "object": "chat.completion",
        }
    )


class FakeGroq:
    """Records every create() call and replays a scripted list of outcomes."""

    def __init__(self, outcomes):
        self.calls: list[dict] = []
        self._outcomes = list(outcomes)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, ChatCompletion):
            return outcome
        return _reply(outcome)


@pytest.fixture(autouse=True)
def _clear_mode_cache():
    groq_client._MODE_CACHE.clear()
    groq_client._client.cache_clear()
    yield
    groq_client._MODE_CACHE.clear()
    groq_client._client.cache_clear()


def _install(monkeypatch: pytest.MonkeyPatch, outcomes) -> FakeGroq:
    fake = FakeGroq(outcomes)
    monkeypatch.setattr(groq_client, "_client", lambda: fake)
    return fake


# --- strict schema ---------------------------------------------------------------------


def test_client_initialization_preserves_timeout_and_retry_policy(monkeypatch) -> None:
    captured: dict = {}
    sentinel = object()

    def fake_constructor(**kwargs):
        captured.update(kwargs)
        return sentinel

    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_key", "configured-test-key", raising=False)
    monkeypatch.setattr(settings, "groq_timeout_seconds", 17.5, raising=False)
    monkeypatch.setattr(groq_client, "Groq", fake_constructor)
    groq_client._client.cache_clear()

    assert groq_client._client() is sentinel
    assert captured == {
        "api_key": "configured-test-key",
        "timeout": 17.5,
        "max_retries": 4,
    }


def test_strict_json_schema_is_strict_and_annotation_free() -> None:
    payload = strict_json_schema(ExtractedComplaintFields)

    assert payload["type"] == "json_schema"
    assert payload["json_schema"]["strict"] is True
    schema = payload["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    # Strict structured output requires every property to be listed as required.
    assert set(schema["required"]) == set(schema["properties"])
    # Pydantic's human annotations are not part of the contract.
    assert "default" not in str(schema)
    assert "title" not in str(schema)
    # $refs must be inlined — a provider cannot disambiguate a `$ref | null` union.
    assert "$defs" not in schema
    assert "$ref" not in str(schema)


def test_optional_enum_becomes_a_single_nullable_node() -> None:
    """Groq rejects `anyOf: [enum, null]` outright; it must be flattened. Verified against the
    live API: with this flattening the schema is accepted, without it, it is a 400."""
    schema = strict_json_schema(ExtractedComplaintFields)["json_schema"]["schema"]

    source = schema["properties"]["complaint_source"]

    assert "anyOf" not in source
    assert source["type"] == ["string", "null"]
    assert "customer_email" in source["enum"]
    assert None in source["enum"]


def test_optional_scalar_becomes_a_nullable_type() -> None:
    schema = strict_json_schema(ExtractedComplaintFields)["json_schema"]["schema"]

    assert schema["properties"]["customer_name"]["type"] == ["string", "null"]
    assert schema["properties"]["quantity_affected"]["type"] == ["number", "null"]


# --- response-mode tiering -------------------------------------------------------------


def test_json_schema_mode_is_preferred_when_a_schema_is_given(monkeypatch) -> None:
    fake = _install(monkeypatch, ['{"product_name": "Cardiostat"}'])

    complete_json("sys", "user", schema=ExtractedComplaintFields)

    assert fake.calls[0]["response_format"]["type"] == "json_schema"


def test_json_object_mode_is_used_when_no_schema_is_given(monkeypatch) -> None:
    fake = _install(monkeypatch, ['{"summary": "ok"}'])

    complete_json("sys", "user")

    assert fake.calls[0]["response_format"] == {"type": "json_object"}


def test_reasoning_effort_is_capped_so_the_answer_fits_in_the_budget(monkeypatch) -> None:
    """gpt-oss bills its chain of thought against max_completion_tokens. At the default
    effort a 900-token budget was measured spending 831 tokens thinking and returning a
    truncated answer, which the caller can only see as unparseable JSON."""
    fake = _install(monkeypatch, ['{"a": 1}', "plain text"])

    complete_json("sys", "user")
    complete_text("sys", "user")

    assert fake.calls[0]["reasoning_effort"] == "low"
    assert fake.calls[1]["reasoning_effort"] == "low"


def test_reasoning_effort_is_omitted_for_a_model_without_one(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "groq_reasoning_effort", "", raising=False)
    fake = _install(monkeypatch, ['{"a": 1}'])

    complete_json("sys", "user")

    assert "reasoning_effort" not in fake.calls[0]


def test_rejected_mode_downgrades_and_is_remembered(monkeypatch) -> None:
    fake = _install(
        monkeypatch,
        [_bad_request("response_format json_schema not supported"), '{"a": 1}', '{"b": 2}'],
    )

    complete_json("sys", "user", schema=ExtractedComplaintFields)
    complete_json("sys", "user", schema=ExtractedComplaintFields)

    modes = [call.get("response_format", {}).get("type", "text") for call in fake.calls]
    # json_schema rejected -> json_object; the second call starts at json_object directly.
    assert modes == ["json_schema", "json_object", "json_object"]


def test_a_schema_less_downgrade_does_not_demote_later_schema_calls(monkeypatch) -> None:
    """A schema-less call can never reach json_schema, so its best mode says nothing about
    whether the model still accepts structured output. Sharing one cache entry between the
    two made a single completeness/summary downgrade silently strip the schema off every
    later extraction — the model then answered in prose and the request failed as a 503."""
    fake = _install(
        monkeypatch,
        [_bad_request("json_object is not supported"), "{}", '{"product_name": "Cardiostat"}'],
    )

    complete_json("sys", "user")  # no schema: json_object rejected -> text
    complete_json("sys", "user", schema=ExtractedComplaintFields)

    modes = [call.get("response_format", {}).get("type", "text") for call in fake.calls]
    assert modes == ["json_object", "text", "json_schema"]


def test_falls_all_the_way_back_to_prompt_only_json(monkeypatch) -> None:
    fake = _install(
        monkeypatch,
        [_bad_request("bad response_format"), _bad_request("bad json_object"), '{"a": 1}'],
    )

    assert complete_json("sys", "user", schema=ExtractedComplaintFields) == {"a": 1}
    assert "response_format" not in fake.calls[-1]


# --- failure separation ----------------------------------------------------------------


def test_provider_failure_falls_back_to_the_second_model(monkeypatch) -> None:
    fake = _install(monkeypatch, [_rate_limit(), '{"a": 1}'])

    assert complete_json("sys", "user") == {"a": 1}
    assert fake.calls[0]["model"] != fake.calls[1]["model"]


def test_all_models_failing_raises_a_client_safe_error(monkeypatch) -> None:
    _install(monkeypatch, [_rate_limit(), _rate_limit()])

    with pytest.raises(LLMError) as excinfo:
        complete_json("sys", "user")

    assert "unavailable" in str(excinfo.value)


def test_unparseable_output_does_not_switch_models(monkeypatch) -> None:
    """A malformed reply is a shape problem — the graph repairs it, the fallback model is not
    a fix for it and must not be spent."""
    fake = _install(monkeypatch, ["I cannot help with that.", '{"a": 1}'])

    with pytest.raises(LLMOutputError) as excinfo:
        complete_json("sys", "user")

    assert len(fake.calls) == 1
    assert excinfo.value.raw_output == "I cannot help with that."


@pytest.mark.parametrize(
    "response",
    [
        _reply(None),
        _reply("   "),
        _reply("unused", choices=False),
    ],
)
def test_empty_or_choice_less_json_response_is_rejected_without_model_switch(
    monkeypatch,
    response: ChatCompletion,
) -> None:
    fake = _install(monkeypatch, [response, '{"a": 1}'])

    with pytest.raises(LLMOutputError, match="empty|choices"):
        complete_json("sys", "user")

    assert len(fake.calls) == 1


def test_timeout_uses_the_configured_fallback_model(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    fake = _install(monkeypatch, [APITimeoutError(request), '{"a": 1}'])

    assert complete_json("sys", "user") == {"a": 1}
    assert fake.calls[0]["model"] != fake.calls[1]["model"]


def test_text_completion_uses_new_token_parameter_and_rejects_empty_output(monkeypatch) -> None:
    fake = _install(monkeypatch, [_reply(None)])

    with pytest.raises(LLMOutputError, match="empty"):
        complete_text("sys", "user", max_tokens=321)

    assert fake.calls[0]["max_completion_tokens"] == 321
    assert "max_tokens" not in fake.calls[0]


def test_vision_uses_first_class_reasoning_and_json_mode(monkeypatch) -> None:
    fake = _install(
        monkeypatch,
        ['{"pages":[{"page_number":1,"text":"Batch CC26045"}]}'],
    )

    result = complete_vision_json("Transcribe", [b"jpeg-page"], max_tokens=777)

    assert result["pages"][0]["text"] == "Batch CC26045"
    call = fake.calls[0]
    assert call["reasoning_effort"] == "none"
    assert "extra_body" not in call
    assert call["max_completion_tokens"] == 777
    assert call["response_format"] == {"type": "json_object"}
    assert call["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/jpeg;base64,"
    )


def test_vision_json_mode_rejection_retries_without_response_format(monkeypatch) -> None:
    fake = _install(
        monkeypatch,
        [
            _bad_request("response_format json_object is unsupported"),
            '{"pages":[{"page_number":1,"text":"Readable"}]}',
        ],
    )

    assert complete_vision_json("Transcribe", [b"jpeg-page"])["pages"][0]["text"] == "Readable"
    assert "response_format" in fake.calls[0]
    assert "response_format" not in fake.calls[1]


def test_vision_rate_limit_is_wrapped_in_client_safe_error(monkeypatch) -> None:
    _install(monkeypatch, [_rate_limit()])

    with pytest.raises(LLMError, match="temporarily unavailable"):
        complete_vision_json("Transcribe", [b"jpeg-page"])


def test_llm_output_error_is_an_llm_error() -> None:
    """Nodes catch LLMError broadly; the subclass must not escape their handlers."""
    assert issubclass(LLMOutputError, LLMError)
