"""Schemas describing what the AI workflow returns.

These are also the schemas the LLM output is validated against. If the model returns
something that does not fit, validation fails and the graph runs a repair attempt.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.enums import (
    ComplaintSource,
    ComplaintType,
    Priority,
    RiskLevel,
    Severity,
)

# Strings the LLM likes to emit instead of a real null.
_NULLISH = {"", "null", "none", "n/a", "na", "unknown", "not specified", "not provided", "-", "--"}

_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y", "%b %Y", "%B %Y")


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip().lower() in _NULLISH:
        return None
    return value


def _coerce_date(value: Any) -> Any:
    """Accept the handful of date shapes an LLM realistically produces; refuse the rest."""
    value = _blank_to_none(value)
    if value is None or isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        return parsed
    # Unparseable date -> drop it rather than guess. A wrong batch date is worse than a blank one.
    return None


def _coerce_enum(value: Any, enum_cls: type) -> Any:
    """Map free text onto the controlled vocabulary; unknown values become None."""
    value = _blank_to_none(value)
    if value is None:
        return None
    normalised = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    members = {member.value for member in enum_cls}
    if normalised in members:
        return normalised
    return None


class ExtractedComplaintFields(BaseModel):
    """Facts pulled out of the complaint text. Everything is optional on purpose:
    an absent value must stay absent rather than be invented."""

    model_config = ConfigDict(extra="ignore")

    complaint_source: ComplaintSource | None = None
    customer_name: str | None = None
    customer_contact: str | None = None
    product_name: str | None = None
    product_strength_grade: str | None = None
    batch_lot_number: str | None = None
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    quantity_affected: float | None = None
    quantity_unit: str | None = None
    complaint_type: ComplaintType | None = None
    complaint_date: date | None = None
    complaint_details: str | None = None
    initial_severity: Severity | None = None
    priority: Priority | None = None

    @field_validator(
        "customer_name",
        "customer_contact",
        "product_name",
        "product_strength_grade",
        "batch_lot_number",
        "quantity_unit",
        "complaint_details",
        mode="before",
    )
    @classmethod
    def _clean_text(cls, value: Any) -> Any:
        value = _blank_to_none(value)
        return value.strip() if isinstance(value, str) else value

    @field_validator("manufacturing_date", "expiry_date", "complaint_date", mode="before")
    @classmethod
    def _clean_date(cls, value: Any) -> Any:
        return _coerce_date(value)

    @field_validator("quantity_affected", mode="before")
    @classmethod
    def _clean_quantity(cls, value: Any) -> Any:
        value = _blank_to_none(value)
        if value is None or isinstance(value, (int, float)):
            return value
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        return float(match.group()) if match else None

    @field_validator("complaint_source", mode="before")
    @classmethod
    def _clean_source(cls, value: Any) -> Any:
        return _coerce_enum(value, ComplaintSource)

    @field_validator("complaint_type", mode="before")
    @classmethod
    def _clean_type(cls, value: Any) -> Any:
        return _coerce_enum(value, ComplaintType)

    @field_validator("initial_severity", mode="before")
    @classmethod
    def _clean_severity(cls, value: Any) -> Any:
        return _coerce_enum(value, Severity)

    @field_validator("priority", mode="before")
    @classmethod
    def _clean_priority(cls, value: Any) -> Any:
        return _coerce_enum(value, Priority)


class CompletenessAssessment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: int = Field(default=0, ge=0, le=100)
    is_complete: bool = False
    missing_critical_fields: list[str] = Field(default_factory=list)
    missing_optional_fields: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    risk_level: RiskLevel = RiskLevel.UNKNOWN
    severity: Severity = Severity.UNKNOWN
    priority: Priority = Priority.MEDIUM
    patient_safety_concern: bool = False
    product_quality_concern: bool = False
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("risk_level", mode="before")
    @classmethod
    def _clean_risk(cls, value: Any) -> Any:
        return _coerce_enum(value, RiskLevel) or RiskLevel.UNKNOWN

    @field_validator("severity", mode="before")
    @classmethod
    def _clean_severity(cls, value: Any) -> Any:
        return _coerce_enum(value, Severity) or Severity.UNKNOWN

    @field_validator("priority", mode="before")
    @classmethod
    def _clean_priority(cls, value: Any) -> Any:
        return _coerce_enum(value, Priority) or Priority.MEDIUM

    @field_validator("confidence", mode="before")
    @classmethod
    def _clean_confidence(cls, value: Any) -> Any:
        try:
            return min(max(float(value), 0.0), 1.0)
        except (TypeError, ValueError):
            return 0.0


class ComplaintRecommendations(BaseModel):
    model_config = ConfigDict(extra="ignore")

    possible_root_causes: list[str] = Field(default_factory=list)
    initial_investigation_steps: list[str] = Field(default_factory=list)
    preliminary_capa_suggestions: list[str] = Field(default_factory=list)


class ComplaintAnalysisRequest(BaseModel):
    """JSON body accepted by /analyze when no file is uploaded."""

    complaint_text: str | None = None


class DuplicateCandidate(BaseModel):
    complaint_id: int
    complaint_number: str
    product_name: str | None = None
    batch_lot_number: str | None = None
    complaint_type: str | None = None
    similarity: float = Field(ge=0.0, le=1.0)
    reason: str


class SourceDocument(BaseModel):
    """One reporter-supplied attachment and the text recovered from it."""

    filename: str
    media_type: str
    extraction_method: Literal["native_text", "groq_vision", "mixed"]
    text: str
    page_count: int = Field(default=1, ge=1)
    ocr_used: bool = False


class VisionOcrPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str


class VisionOcrResult(BaseModel):
    pages: list[VisionOcrPage] = Field(default_factory=list)


class ComplaintAnalysisResponse(BaseModel):
    """The full payload the frontend uses to populate the form and the AI panel."""

    extracted_fields: ExtractedComplaintFields
    completeness: CompletenessAssessment
    risk_assessment: RiskAssessment
    summary: str = ""
    recommendations: ComplaintRecommendations
    warnings: list[str] = Field(default_factory=list)
    duplicate_candidates: list[DuplicateCandidate] = Field(default_factory=list)
    original_text: str = ""
    input_filename: str | None = None
    source_documents: list[SourceDocument] = Field(default_factory=list)
    # Constant reminder carried all the way to the UI: this is decision support, not a decision.
    disclaimer: str = (
        "AI-generated analysis. Preliminary only — every field, risk rating and CAPA suggestion "
        "must be reviewed and approved by qualified QA / pharmacovigilance personnel."
    )
