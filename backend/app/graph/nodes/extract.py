"""Nodes 2 and 2b — structured extraction, and the repair attempt when it comes back malformed."""

from __future__ import annotations

import json
import logging

from app.graph.state import GraphState
from app.llm.groq_client import LLMError, LLMOutputError, complete_json
from app.llm.prompts import EXTRACTION_SYSTEM, REPAIR_SYSTEM
from app.schemas.analysis import ExtractedComplaintFields

logger = logging.getLogger(__name__)

NOT_JSON_ERROR = "The model's reply could not be read as JSON."


def _wrap_document(text: str) -> str:
    """The complaint is always delimited so the model can tell data from instructions."""
    return f"<complaint>\n{text}\n</complaint>\n\nExtract the JSON object now."


def extract_complaint_fields(state: GraphState) -> dict:
    """Ask the LLM for the structured fields.

    Two different failures are handled differently:
      * unusable output -> keep the raw reply and let the repair node fix it;
      * provider failure -> mark the LLM unavailable, and the rest of the workflow falls back
        to deterministic behaviour.
    """
    try:
        raw = complete_json(
            EXTRACTION_SYSTEM,
            _wrap_document(state["raw_text"]),
            max_tokens=1200,
            schema=ExtractedComplaintFields,
        )
    except LLMOutputError as exc:
        logger.info("Extraction returned non-JSON output; handing it to the repair node.")
        return {"raw_extraction": None, "raw_output": exc.raw_output, "extraction_error": NOT_JSON_ERROR}
    except LLMError as exc:
        logger.warning("Extraction call failed: %s", exc)
        return {
            "raw_extraction": None,
            "raw_output": None,
            "llm_available": False,
            "errors": [str(exc)],
            "warnings": ["AI extraction was unavailable — the form could not be pre-filled."],
        }
    return {"raw_extraction": raw, "raw_output": None}


def repair_extraction(state: GraphState) -> dict:
    """Second chance: hand the bad output back with the reason it was rejected.

    Only reachable from the conditional edge in workflow.py, and only while
    retry_count < settings.max_extraction_retries.
    """
    if state.get("raw_extraction"):
        previous = json.dumps(state["raw_extraction"], default=str)[:4000]
    else:
        # The reply was not JSON at all — show the model what it actually sent.
        previous = (state.get("raw_output") or "")[:4000]

    user_prompt = (
        "The following output failed schema validation.\n"
        f"Validation error:\n{state.get('extraction_error')}\n\n"
        f"Invalid output:\n{previous}\n\n"
        "Return the corrected JSON object with the same keys. Keep null where a value is "
        "unknown; do not invent values."
    )
    try:
        raw = complete_json(
            REPAIR_SYSTEM, user_prompt, max_tokens=1200, schema=ExtractedComplaintFields
        )
    except LLMOutputError as exc:
        return {
            "retry_count": state.get("retry_count", 0) + 1,
            "raw_extraction": None,
            "raw_output": exc.raw_output,
            "extraction_error": NOT_JSON_ERROR,
        }
    except LLMError as exc:
        logger.warning("Repair call failed: %s", exc)
        return {
            "retry_count": state.get("retry_count", 0) + 1,
            "llm_available": False,
            "errors": [str(exc)],
        }
    return {
        "raw_extraction": raw,
        "raw_output": None,
        "retry_count": state.get("retry_count", 0) + 1,
    }
