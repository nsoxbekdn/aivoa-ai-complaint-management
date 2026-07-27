"""Tests for the LangGraph workflow itself: the repair loop and graceful degradation."""

import pytest

from app.graph.workflow import build_graph, run_analysis
from app.llm.groq_client import LLMError, LLMOutputError
from tests.conftest import FAKE_EXTRACTION, fake_complete_json

TEXT = (
    "Batch AMX-24118 of Amoxinova 500 mg Capsules arrived with 12 cracked capsules. "
    "Reported by Meridian Pharmacy Group on 2026-06-14."
)

NODE_MODULES = (
    "app.graph.nodes.extract",
    "app.graph.nodes.completeness_node",
    "app.graph.nodes.risk",
    "app.graph.nodes.summary",
    "app.graph.nodes.recommendations",
)


def test_graph_contains_every_declared_node() -> None:
    nodes = build_graph().get_graph().nodes

    assert {
        "prepare_input",
        "extract_complaint_fields",
        "validate_extraction",
        "repair_extraction",
        "assess_completeness",
        "classify_risk",
        "generate_summary",
        "generate_recommendations",
        "assemble_result",
    } <= set(nodes)


def test_invalid_extraction_triggers_one_repair_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def flaky(
        system_prompt: str, user_prompt: str, *, max_tokens: int = 1200, schema: object = None
    ) -> dict:
        if "intake assistant" in system_prompt:
            calls.append("extract")
            # complaint_details must be a string; a dict fails Pydantic validation.
            return dict(FAKE_EXTRACTION) | {"complaint_details": {"unexpected": "object"}}
        if "malformed JSON" in system_prompt:
            calls.append("repair")
            return dict(FAKE_EXTRACTION)
        return fake_complete_json(system_prompt, user_prompt, max_tokens=max_tokens)

    for module in NODE_MODULES:
        monkeypatch.setattr(f"{module}.complete_json", flaky)

    result = run_analysis(TEXT)

    assert calls == ["extract", "repair"]  # exactly one repair attempt
    assert result.extracted_fields.batch_lot_number == "AMX-24118"


def test_repair_is_attempted_at_most_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def always_broken(
        system_prompt: str, user_prompt: str, *, max_tokens: int = 1200, schema: object = None
    ) -> dict:
        if "intake assistant" in system_prompt or "malformed JSON" in system_prompt:
            calls.append("extract-or-repair")
            return {"complaint_details": {"still": "broken"}}
        return fake_complete_json(system_prompt, user_prompt, max_tokens=max_tokens)

    for module in NODE_MODULES:
        monkeypatch.setattr(f"{module}.complete_json", always_broken)

    result = run_analysis(TEXT)

    assert len(calls) == 2  # initial attempt + one repair, then the graph moves on
    assert result.extracted_fields.batch_lot_number is None
    assert any("could not be validated" in warning for warning in result.warnings)


def test_non_json_reply_is_repaired_rather_than_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model answers with prose. That must reach the repair node, not kill the request."""
    calls: list[str] = []

    def prose_then_json(system_prompt: str, user_prompt: str, *, max_tokens: int = 1200, schema=None):
        if "intake assistant" in system_prompt:
            calls.append("extract")
            raise LLMOutputError("not json", raw_output="Sure! Here is what I found: ...")
        if "malformed JSON" in system_prompt:
            calls.append("repair")
            # The repair prompt must show the model its own unusable reply.
            assert "Sure! Here is what I found" in user_prompt
            return dict(FAKE_EXTRACTION)
        return fake_complete_json(system_prompt, user_prompt, max_tokens=max_tokens)

    for module in NODE_MODULES:
        monkeypatch.setattr(f"{module}.complete_json", prose_then_json)

    result = run_analysis(TEXT)

    assert calls == ["extract", "repair"]
    assert result.extracted_fields.batch_lot_number == "AMX-24118"


def test_persistently_non_json_reply_degrades_with_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def always_prose(system_prompt: str, user_prompt: str, *, max_tokens: int = 1200, schema=None):
        if "intake assistant" in system_prompt or "malformed JSON" in system_prompt:
            calls.append("extract-or-repair")
            raise LLMOutputError("not json", raw_output="still prose")
        return fake_complete_json(system_prompt, user_prompt, max_tokens=max_tokens)

    for module in NODE_MODULES:
        monkeypatch.setattr(f"{module}.complete_json", always_prose)

    result = run_analysis(TEXT)

    assert len(calls) == 2  # initial attempt + one repair, then the graph moves on
    assert result.extracted_fields.product_name is None
    assert any("could not be validated" in warning for warning in result.warnings)
    # The rest of the workflow still ran.
    assert result.risk_assessment.risk_level != "unknown"
    assert result.completeness.follow_up_questions


def test_workflow_degrades_gracefully_when_the_provider_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def dead(*_args, **_kwargs) -> dict:
        raise LLMError("AI provider unavailable (simulated).")

    for module in NODE_MODULES:
        monkeypatch.setattr(f"{module}.complete_json", dead)

    result = run_analysis("Possible contamination found in a sterile injectable vial.")

    # No crash: deterministic rules still produce a usable triage.
    assert result.risk_assessment.risk_level == "critical"
    assert result.completeness.follow_up_questions
    assert result.summary
    assert any("unavailable" in warning.lower() for warning in result.warnings)


def test_oversized_input_is_truncated_with_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in NODE_MODULES:
        monkeypatch.setattr(f"{module}.complete_json", fake_complete_json)

    result = run_analysis("A" * 60_000)

    assert any("truncated" in warning for warning in result.warnings)
    assert len(result.original_text) <= 40_000
