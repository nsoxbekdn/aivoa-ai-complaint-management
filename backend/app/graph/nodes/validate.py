"""Node 3 — validate the model output against the Pydantic schema and against the source text.

Two different questions are answered here:
  * is the JSON *shaped* correctly?  -> Pydantic. If not, the graph routes to repair.
  * is each identifier *actually in the document*? -> grounding guard. If not, the value is
    dropped, because a plausible-but-invented batch number is the worst failure mode this
    system can have.
"""

from __future__ import annotations

import re

from pydantic import ValidationError

from app.config import get_settings
from app.graph.state import GraphState
from app.schemas.analysis import ExtractedComplaintFields

# Verbatim fields: these must appear in the source text character-for-character (ignoring
# punctuation and case). Free-text fields are excluded — the model is allowed to rephrase those.
VERBATIM_FIELDS = ("batch_lot_number", "customer_contact", "product_strength_grade")

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalise(value: str) -> str:
    return _NON_ALNUM.sub("", value.lower())


def _ground_fields(fields: ExtractedComplaintFields, source: str) -> tuple[ExtractedComplaintFields, list[str]]:
    """Drop verbatim values that do not occur in the source document."""
    warnings: list[str] = []
    haystack = _normalise(source)
    updates: dict[str, None] = {}

    for name in VERBATIM_FIELDS:
        value = getattr(fields, name)
        if isinstance(value, str) and value and _normalise(value) not in haystack:
            updates[name] = None
            warnings.append(
                f"Discarded AI value for '{name.replace('_', ' ')}' because it does not appear "
                "in the source document."
            )

    quantity = fields.quantity_affected
    if quantity is not None:
        digits = str(int(quantity)) if float(quantity).is_integer() else str(quantity)
        if digits not in re.sub(r"[^0-9.]", "", source):
            updates["quantity_affected"] = None
            warnings.append(
                "Discarded AI value for 'quantity affected' because that number does not appear "
                "in the source document."
            )

    if updates:
        fields = fields.model_copy(update=updates)
    return fields, warnings


def _out_of_retries_warning(state: GraphState) -> list[str]:
    if state.get("retry_count", 0) < get_settings().max_extraction_retries:
        return []
    return ["AI extraction could not be validated after retrying; the form was left blank."]


def validate_extraction(state: GraphState) -> dict:
    """Turn raw_extraction into a validated ExtractedComplaintFields, or flag it for repair."""
    raw = state.get("raw_extraction")

    if raw is None:
        if state.get("raw_output"):
            # The model answered, but not with JSON. That is repairable, not fatal.
            return {
                "extraction_valid": False,
                "extracted_fields": ExtractedComplaintFields(),
                "warnings": _out_of_retries_warning(state),
            }
        # The LLM was unreachable. Continue with an empty (but valid) field set so the user
        # still gets the deterministic completeness and risk output.
        return {"extracted_fields": ExtractedComplaintFields(), "extraction_valid": True}

    try:
        fields = ExtractedComplaintFields.model_validate(raw)
    except ValidationError as exc:
        # A Pydantic failure is a shape problem, not a provider problem: it is repaired by the
        # graph (below), never by switching to the fallback model.
        return {
            "extraction_valid": False,
            "extraction_error": exc.json(include_url=False)[:1500],
            "extracted_fields": ExtractedComplaintFields(),
            "warnings": _out_of_retries_warning(state),
        }

    fields, warnings = _ground_fields(fields, state.get("raw_text", ""))
    return {"extracted_fields": fields, "extraction_valid": True, "warnings": warnings}


def route_after_validation(state: GraphState) -> str:
    """Conditional edge: repair once (at most) before moving on."""
    if state.get("extraction_valid"):
        return "assess_completeness"
    if not state.get("llm_available", True):
        return "assess_completeness"
    if state.get("retry_count", 0) < get_settings().max_extraction_retries:
        return "repair_extraction"
    return "assess_completeness"
