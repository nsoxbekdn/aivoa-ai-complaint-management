"""Node 7 — preliminary root causes, investigation steps and CAPA suggestions."""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from app.graph.state import GraphState
from app.llm.groq_client import LLMError, complete_json
from app.llm.prompts import RECOMMENDATIONS_SYSTEM
from app.schemas.analysis import ComplaintRecommendations, ExtractedComplaintFields

logger = logging.getLogger(__name__)

# Generic GMP starting points, used only when the LLM is unavailable. Intentionally generic —
# a specific-sounding but unfounded root cause would be worse than none.
_FALLBACK = ComplaintRecommendations(
    possible_root_causes=[
        "To be determined by investigation — no AI analysis available for this complaint.",
    ],
    initial_investigation_steps=[
        "Review the batch manufacturing and packaging records for the affected batch.",
        "Inspect the retained sample for the reported defect.",
        "Check whether similar complaints exist for the same product or batch.",
    ],
    preliminary_capa_suggestions=[
        "Open a quality investigation and assign an owner before proposing any CAPA.",
    ],
)


def generate_recommendations(state: GraphState) -> dict:
    fields: ExtractedComplaintFields = state.get("extracted_fields") or ExtractedComplaintFields()
    risk = state.get("risk_assessment")

    if not state.get("llm_available", True):
        return {"recommendations": _FALLBACK}

    user_prompt = (
        f"<complaint>\n{state.get('raw_text', '')}\n</complaint>\n\n"
        f"Extracted fields:\n{json.dumps(fields.model_dump(mode='json'), indent=2)}\n"
        f"Preliminary risk level: {risk.risk_level if risk else 'unknown'}\n\n"
        "Return the recommendations JSON now."
    )
    try:
        raw = complete_json(
            RECOMMENDATIONS_SYSTEM, user_prompt, max_tokens=900, schema=ComplaintRecommendations
        )
        recommendations = ComplaintRecommendations.model_validate(raw)
    except (LLMError, ValidationError) as exc:
        logger.info("Recommendation generation failed: %s", type(exc).__name__)
        return {
            "recommendations": _FALLBACK,
            "warnings": ["AI recommendations were unavailable; generic GMP steps are shown."],
        }

    return {"recommendations": recommendations}
