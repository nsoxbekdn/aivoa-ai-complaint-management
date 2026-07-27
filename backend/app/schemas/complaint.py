"""Request/response schemas for the complaint CRUD endpoints."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.analysis import ExtractedComplaintFields, SourceDocument
from app.schemas.intake import IntakeChatMessage
from app.schemas.enums import (
    ComplaintSource,
    ComplaintStatus,
    ComplaintType,
    Priority,
    RiskLevel,
    Severity,
)


class ComplaintBase(BaseModel):
    """Fields a human can edit. Optional here; ComplaintCreate tightens what is mandatory."""

    complaint_source: ComplaintSource | None = None
    customer_name: str | None = Field(default=None, max_length=255)
    customer_contact: str | None = Field(default=None, max_length=255)

    product_name: str | None = Field(default=None, max_length=255)
    product_strength_grade: str | None = Field(default=None, max_length=128)
    batch_lot_number: str | None = Field(default=None, max_length=128)
    manufacturing_date: date | None = None
    expiry_date: date | None = None
    quantity_affected: float | None = Field(default=None, ge=0)
    quantity_unit: str | None = Field(default=None, max_length=64)

    complaint_type: ComplaintType | None = None
    complaint_date: date | None = None
    complaint_details: str | None = None

    initial_severity: Severity | None = None
    priority: Priority | None = None

    # AI output the reviewer decided to keep on the record.
    risk_level: RiskLevel | None = None
    risk_rationale: str | None = None
    risk_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    patient_safety_concern: bool | None = None
    product_quality_concern: bool | None = None
    ai_summary: str | None = None
    completeness_score: int | None = Field(default=None, ge=0, le=100)
    missing_fields: list[str] | None = None
    root_cause_recommendations: list[str] | None = None
    initial_investigation_steps: list[str] | None = None
    capa_recommendations: list[str] | None = None
    duplicate_candidates: list[dict] | None = None
    analysis_warnings: list[str] | None = None

    original_text: str | None = None
    input_filename: str | None = Field(default=None, max_length=255)
    intake_transcript: list[dict] | None = None
    source_documents: list[dict] | None = None
    status: ComplaintStatus = ComplaintStatus.OPEN

    @model_validator(mode="after")
    def _check_date_consistency(self) -> "ComplaintBase":
        if self.manufacturing_date and self.expiry_date and self.expiry_date < self.manufacturing_date:
            raise ValueError("expiry_date cannot be earlier than manufacturing_date")
        if self.complaint_date and self.complaint_date > date.today():
            raise ValueError("complaint_date cannot be in the future")
        return self


class ComplaintCreate(ComplaintBase):
    """What the frontend posts after the reviewer has checked the AI suggestions."""

    complaint_source: ComplaintSource
    product_name: str = Field(min_length=1, max_length=255)
    complaint_type: ComplaintType
    complaint_date: date
    complaint_details: str = Field(min_length=10)
    initial_severity: Severity
    priority: Priority


class ComplaintUpdate(ComplaintBase):
    """Partial update — every field stays optional."""

    status: ComplaintStatus | None = None


class ComplaintRead(ComplaintBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    complaint_number: str
    created_at: datetime
    updated_at: datetime


class ComplaintListResponse(BaseModel):
    items: list[ComplaintRead]
    total: int
    limit: int
    offset: int


class ComplaintFinalizeRequest(BaseModel):
    """Final reporter facts plus provenance; the server regenerates all internal QA output."""

    fields: ExtractedComplaintFields
    original_text: str = ""
    input_filename: str | None = Field(default=None, max_length=255)
    intake_transcript: list[IntakeChatMessage] = Field(default_factory=list, max_length=100)
    source_documents: list[SourceDocument] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _require_lodgeable_facts(self) -> "ComplaintFinalizeRequest":
        required = {
            "complaint_source": self.fields.complaint_source,
            "customer_name": self.fields.customer_name,
            "product_name": self.fields.product_name,
            "batch_lot_number": self.fields.batch_lot_number,
            "complaint_type": self.fields.complaint_type,
            "complaint_date": self.fields.complaint_date,
            "complaint_details": self.fields.complaint_details,
        }
        missing = [name for name, value in required.items() if value is None or value == ""]
        quantity_critical = {
            "product_quality_defect",
            "packaging_defect",
            "contamination",
            "wrong_product_or_strength",
            "labelling_error",
        }
        if self.fields.complaint_type in quantity_critical and self.fields.quantity_affected is None:
            missing.append("quantity_affected")
        if missing:
            raise ValueError(f"Missing required complaint facts: {', '.join(missing)}")
        if (
            self.fields.manufacturing_date
            and self.fields.expiry_date
            and self.fields.expiry_date < self.fields.manufacturing_date
        ):
            raise ValueError("expiry_date cannot be earlier than manufacturing_date")
        if self.fields.complaint_date and self.fields.complaint_date > date.today():
            raise ValueError("complaint_date cannot be in the future")
        if self.fields.complaint_details and len(self.fields.complaint_details.strip()) < 10:
            raise ValueError("complaint_details must contain at least 10 characters")
        return self


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    answer: str
    grounded_in: str
