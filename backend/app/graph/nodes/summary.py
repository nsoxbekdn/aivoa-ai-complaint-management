"""Node 6 — a short factual summary for the reviewer."""

from __future__ import annotations

import logging

from app.graph.state import GraphState
from app.llm.groq_client import LLMError, complete_json
from app.llm.prompts import SUMMARY_SYSTEM
from app.schemas.analysis import ExtractedComplaintFields

logger = logging.getLogger(__name__)


def _fallback_summary(fields: ExtractedComplaintFields, raw_text: str) -> str:
    """No LLM: state the facts we hold, and say plainly that this is not an AI summary."""
    parts: list[str] = []
    if fields.product_name:
        parts.append(f"Complaint about {fields.product_name}")
        if fields.batch_lot_number:
            parts[-1] += f" (batch {fields.batch_lot_number})"
    if fields.quantity_affected is not None:
        quantity = (
            int(fields.quantity_affected)
            if float(fields.quantity_affected).is_integer()
            else fields.quantity_affected
        )
        parts.append(f"{quantity} {fields.quantity_unit or 'unit(s)'} affected.")
    date_facts: list[str] = []
    if fields.manufacturing_date:
        date_facts.append(f"manufactured {fields.manufacturing_date.isoformat()}")
    if fields.expiry_date:
        date_facts.append(f"expires {fields.expiry_date.isoformat()}")
    if date_facts:
        parts.append("Product dates: " + "; ".join(date_facts) + ".")
    if fields.complaint_date:
        parts.append(f"Observed or reported on {fields.complaint_date.isoformat()}.")
    if fields.complaint_details:
        parts.append(fields.complaint_details)
    elif raw_text:
        parts.append(raw_text[:280].strip() + ("…" if len(raw_text) > 280 else ""))
    return " ".join(parts) or "No summary available."


def generate_summary(state: GraphState) -> dict:
    fields: ExtractedComplaintFields = state.get("extracted_fields") or ExtractedComplaintFields()

    if not state.get("llm_available", True):
        return {"summary": _fallback_summary(fields, state.get("raw_text", ""))}

    user_prompt = (
        f"<complaint>\n{state.get('raw_text', '')}\n</complaint>\n\nReturn the summary JSON now."
    )
    try:
        raw = complete_json(SUMMARY_SYSTEM, user_prompt, max_tokens=900)
        summary = str(raw.get("summary", "")).strip()
    except LLMError as exc:
        logger.info("Summary generation failed: %s", exc)
        return {
            "summary": _fallback_summary(fields, state.get("raw_text", "")),
            "warnings": ["AI summary was unavailable; a factual extract is shown instead."],
        }

    return {"summary": summary or _fallback_summary(fields, state.get("raw_text", ""))}
