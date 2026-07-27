"""The single ORM table of the system: a saved, human-reviewed customer complaint."""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# JSONB on Postgres (indexable, binary), plain JSON on SQLite. Same Python API either way.
JSONField = JSON().with_variant(JSONB(), "postgresql")


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Human-readable identifier, e.g. CC-2026-0001. Unique so concurrent inserts cannot collide.
    complaint_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    # --- origin and customer -------------------------------------------------
    complaint_source: Mapped[str | None] = mapped_column(String(64))
    customer_name: Mapped[str | None] = mapped_column(String(255))
    customer_contact: Mapped[str | None] = mapped_column(String(255))

    # --- product and batch ---------------------------------------------------
    product_name: Mapped[str | None] = mapped_column(String(255), index=True)
    product_strength_grade: Mapped[str | None] = mapped_column(String(128))
    batch_lot_number: Mapped[str | None] = mapped_column(String(128), index=True)
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    quantity_affected: Mapped[float | None] = mapped_column(Float)
    quantity_unit: Mapped[str | None] = mapped_column(String(64))

    # --- complaint -----------------------------------------------------------
    complaint_type: Mapped[str | None] = mapped_column(String(64), index=True)
    complaint_date: Mapped[date | None] = mapped_column(Date)
    complaint_details: Mapped[str | None] = mapped_column(Text)

    # --- human assessment ----------------------------------------------------
    initial_severity: Mapped[str | None] = mapped_column(String(32))
    priority: Mapped[str | None] = mapped_column(String(32))

    # --- AI output ------------------------------------------------------------
    # A provenance snapshot of what the model suggested at intake, kept next to what the
    # reviewer approved. This is NOT a validated QMS audit trail: there is no authenticated
    # user identity, no field-level old/new change history and no electronic signature.
    risk_level: Mapped[str | None] = mapped_column(String(32))
    risk_rationale: Mapped[str | None] = mapped_column(Text)
    risk_confidence: Mapped[float | None] = mapped_column(Float)
    patient_safety_concern: Mapped[bool | None] = mapped_column(Boolean)
    product_quality_concern: Mapped[bool | None] = mapped_column(Boolean)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    completeness_score: Mapped[int | None] = mapped_column()
    missing_fields: Mapped[list | None] = mapped_column(JSONField)
    root_cause_recommendations: Mapped[list | None] = mapped_column(JSONField)
    initial_investigation_steps: Mapped[list | None] = mapped_column(JSONField)
    capa_recommendations: Mapped[list | None] = mapped_column(JSONField)
    duplicate_candidates: Mapped[list | None] = mapped_column(JSONField)
    analysis_warnings: Mapped[list | None] = mapped_column(JSONField)

    # --- provenance ----------------------------------------------------------
    original_text: Mapped[str | None] = mapped_column(Text)
    input_filename: Mapped[str | None] = mapped_column(String(255))
    intake_transcript: Mapped[list | None] = mapped_column(JSONField)
    source_documents: Mapped[list | None] = mapped_column(JSONField)

    status: Mapped[str] = mapped_column(String(32), default="open", server_default="open")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # Supports the duplicate-detection pre-filter (same product + batch).
        Index("ix_complaints_product_batch", "product_name", "batch_lot_number"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Complaint {self.complaint_number} {self.product_name!r}>"
