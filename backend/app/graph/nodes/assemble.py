"""Node 8 — final consistency pass before the state leaves the graph."""

from __future__ import annotations

from app.graph.state import GraphState
from app.schemas.analysis import ExtractedComplaintFields, RiskAssessment


def assemble_result(state: GraphState) -> dict:
    """Align the form's severity/priority with the risk assessment when the text did not
    state them, and add the review reminder."""
    fields: ExtractedComplaintFields = state.get("extracted_fields") or ExtractedComplaintFields()
    risk: RiskAssessment | None = state.get("risk_assessment")

    updates: dict[str, object] = {}
    if risk:
        if fields.initial_severity is None and risk.severity != "unknown":
            updates["initial_severity"] = risk.severity
        if fields.priority is None:
            updates["priority"] = risk.priority
    if updates:
        fields = fields.model_copy(update=updates)

    warnings: list[str] = []
    if risk and risk.patient_safety_concern:
        warnings.append(
            "Possible patient safety impact flagged — escalate to pharmacovigilance / QA "
            "immediately for human assessment."
        )

    return {"extracted_fields": fields, "warnings": warnings}
