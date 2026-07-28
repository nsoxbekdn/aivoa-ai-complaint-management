"""Node 4 — completeness.

The score and the missing-field lists are computed in Python (deterministic, testable).
The LLM is used only to phrase the follow-up questions; if it fails we keep the
rule-based questions.
"""

from __future__ import annotations

import json
import logging

from app.graph.state import GraphState
from app.llm.groq_client import LLMError, complete_json
from app.llm.prompts import COMPLETENESS_SYSTEM
from app.schemas.analysis import ExtractedComplaintFields
from app.services.completeness import assess_completeness

logger = logging.getLogger(__name__)


def assess_completeness_node(state: GraphState) -> dict:
    fields: ExtractedComplaintFields = state.get("extracted_fields") or ExtractedComplaintFields()
    assessment = assess_completeness(fields)

    missing = assessment.missing_critical_fields + assessment.missing_optional_fields
    if not missing or not state.get("llm_available", True):
        return {"completeness": assessment}

    user_prompt = (
        f"Extracted fields:\n{json.dumps(fields.model_dump(mode='json'), indent=2)}\n\n"
        f"Missing fields: {', '.join(missing)}\n"
        f"Complaint type: {fields.complaint_type or 'unknown'}\n\n"
        "Return the follow-up questions JSON now."
    )
    try:
        raw = complete_json(COMPLETENESS_SYSTEM, user_prompt, max_tokens=900)
        questions = [str(q).strip() for q in raw.get("follow_up_questions", []) if str(q).strip()]
        if questions:
            assessment = assessment.model_copy(update={"follow_up_questions": questions[:6]})
    except LLMError as exc:
        logger.info("Follow-up question generation failed, keeping rule-based questions: %s", exc)

    return {"completeness": assessment}
