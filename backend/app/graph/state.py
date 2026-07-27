"""The typed state that flows through the LangGraph workflow.

Every node reads this dict and returns a *partial* dict of updates. `warnings` and `errors`
use an `operator.add` reducer, so a node returns only the new entries and LangGraph appends
them — that keeps nodes independent of each other's history.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.schemas.analysis import (
    ComplaintRecommendations,
    CompletenessAssessment,
    ExtractedComplaintFields,
    RiskAssessment,
)


class GraphState(TypedDict, total=False):
    # --- input -----------------------------------------------------------------
    raw_text: str
    input_type: str  # "text" | "pdf"
    filename: str | None

    # --- extraction ------------------------------------------------------------
    raw_extraction: dict[str, Any] | None  # last unvalidated JSON from the model
    raw_output: str | None  # the model's reply when it could not be parsed as JSON at all
    extraction_error: str | None  # why validation failed, fed to the repair prompt
    extraction_valid: bool
    retry_count: int
    extracted_fields: ExtractedComplaintFields | None

    # --- analysis --------------------------------------------------------------
    completeness: CompletenessAssessment | None
    risk_assessment: RiskAssessment | None
    summary: str
    recommendations: ComplaintRecommendations | None

    # --- bookkeeping -----------------------------------------------------------
    llm_available: bool
    warnings: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]


def initial_state(raw_text: str, input_type: str, filename: str | None, warnings: list[str]) -> GraphState:
    return GraphState(
        raw_text=raw_text,
        input_type=input_type,
        filename=filename,
        raw_extraction=None,
        raw_output=None,
        extraction_error=None,
        extraction_valid=False,
        retry_count=0,
        extracted_fields=None,
        completeness=None,
        risk_assessment=None,
        summary="",
        recommendations=None,
        llm_available=True,
        warnings=list(warnings),
        errors=[],
    )
