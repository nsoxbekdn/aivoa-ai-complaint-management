"""Node 5 — preliminary risk classification.

The rule engine always runs. The LLM opinion is merged on top of it and can only raise the
rating, never lower it.
"""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from app.graph.state import GraphState
from app.llm.groq_client import LLMError, complete_json
from app.llm.prompts import RISK_SYSTEM
from app.schemas.analysis import ExtractedComplaintFields, RiskAssessment
from app.services.risk_rules import heuristic_risk, merge_with_floor

logger = logging.getLogger(__name__)


def classify_risk(state: GraphState) -> dict:
    fields: ExtractedComplaintFields = state.get("extracted_fields") or ExtractedComplaintFields()
    floor = heuristic_risk(state.get("raw_text", ""), fields)

    if not state.get("llm_available", True):
        return {
            "risk_assessment": floor,
            "warnings": ["Risk rating came from the deterministic rule engine only (AI unavailable)."],
        }

    user_prompt = (
        f"<complaint>\n{state.get('raw_text', '')}\n</complaint>\n\n"
        f"Structured fields already extracted:\n"
        f"{json.dumps(fields.model_dump(mode='json'), indent=2)}\n\n"
        "Return the risk assessment JSON now."
    )
    try:
        raw = complete_json(RISK_SYSTEM, user_prompt, max_tokens=600, schema=RiskAssessment)
        model_view = RiskAssessment.model_validate(raw)
    except (LLMError, ValidationError) as exc:
        logger.warning("Risk classification fell back to rules: %s", type(exc).__name__)
        return {
            "risk_assessment": floor,
            "warnings": ["AI risk classification failed; the rule-based rating is shown instead."],
        }

    return {"risk_assessment": merge_with_floor(model_view, floor)}
