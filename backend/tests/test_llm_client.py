"""Groq client behaviour: response-mode tiering, model fallback, and failure separation.

No network: a fake client object replaces `_client()`, so these tests assert exactly which
requests the code would send.
"""

from types import SimpleNamespace

import pytest

from app.llm import groq_client
from app.llm.groq_client import (
    LLMError,
    LLMOutputError,
    complete_json,
    strict_json_schema,
)
from app.schemas.analysis import ExtractedComplaintFields


class FakeBadRequest(Exception):
    """Stands in for the SDK's 400 for an unsupported response_format."""

    status_code = 400


class FakeRateLimit(Exception):
    """Stands in for a genuine provider failure."""


def _reply(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


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
        return _reply(outcome)


@pytest.fixture(autouse=True)
def _clear_mode_cache():
    groq_client._MODE_CACHE.clear()
    yield
    groq_client._MODE_CACHE.clear()


def _install(monkeypatch: pytest.MonkeyPatch, outcomes) -> FakeGroq:
    fake = FakeGroq(outcomes)
    monkeypatch.setattr(groq_client, "_client", lambda: fake)
    return fake


# --- strict schema ---------------------------------------------------------------------


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


def test_rejected_mode_downgrades_and_is_remembered(monkeypatch) -> None:
    fake = _install(
        monkeypatch,
        [FakeBadRequest("response_format json_schema not supported"), '{"a": 1}', '{"b": 2}'],
    )

    complete_json("sys", "user", schema=ExtractedComplaintFields)
    complete_json("sys", "user", schema=ExtractedComplaintFields)

    modes = [call.get("response_format", {}).get("type", "text") for call in fake.calls]
    # json_schema rejected -> json_object; the second call starts at json_object directly.
    assert modes == ["json_schema", "json_object", "json_object"]


def test_falls_all_the_way_back_to_prompt_only_json(monkeypatch) -> None:
    fake = _install(
        monkeypatch,
        [FakeBadRequest("bad response_format"), FakeBadRequest("bad json_object"), '{"a": 1}'],
    )

    assert complete_json("sys", "user", schema=ExtractedComplaintFields) == {"a": 1}
    assert "response_format" not in fake.calls[-1]


# --- failure separation ----------------------------------------------------------------


def test_provider_failure_falls_back_to_the_second_model(monkeypatch) -> None:
    fake = _install(monkeypatch, [FakeRateLimit("429"), '{"a": 1}'])

    assert complete_json("sys", "user") == {"a": 1}
    assert fake.calls[0]["model"] != fake.calls[1]["model"]


def test_all_models_failing_raises_a_client_safe_error(monkeypatch) -> None:
    _install(monkeypatch, [FakeRateLimit("429"), FakeRateLimit("429")])

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


def test_llm_output_error_is_an_llm_error() -> None:
    """Nodes catch LLMError broadly; the subclass must not escape their handlers."""
    assert issubclass(LLMOutputError, LLMError)
