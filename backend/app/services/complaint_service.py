"""Persistence layer for complaints.

Routes stay thin: they validate input and translate exceptions into HTTP. Everything that
touches the database lives here.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.schemas.complaint import ComplaintCreate, ComplaintUpdate

logger = logging.getLogger(__name__)

_NUMBER_PREFIX = "CC"
_MAX_NUMBER_ATTEMPTS = 5


class ComplaintNotFoundError(LookupError):
    pass


def _next_complaint_number(db: Session, year: int) -> str:
    """CC-2026-0001, CC-2026-0002, ...

    Two requests can read the same max value, so this is only a *proposal*: the unique
    constraint on complaint_number is what actually guarantees correctness, and
    `create_complaint` retries on the resulting IntegrityError.
    """
    prefix = f"{_NUMBER_PREFIX}-{year}-"
    latest = db.execute(
        select(func.max(Complaint.complaint_number)).where(Complaint.complaint_number.like(f"{prefix}%"))
    ).scalar_one_or_none()
    sequence = int(latest.rsplit("-", 1)[1]) + 1 if latest else 1
    return f"{prefix}{sequence:04d}"


def create_complaint(db: Session, payload: ComplaintCreate) -> Complaint:
    year = date.today().year
    data = payload.model_dump()

    for attempt in range(_MAX_NUMBER_ATTEMPTS):
        complaint = Complaint(complaint_number=_next_complaint_number(db, year), **data)
        db.add(complaint)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            logger.info("Complaint number collision, retrying (attempt %s).", attempt + 1)
            continue
        db.refresh(complaint)
        return complaint

    raise RuntimeError("Could not allocate a unique complaint number after several attempts.")


def list_complaints(
    db: Session,
    *,
    limit: int = 25,
    offset: int = 0,
    search: str | None = None,
    status: str | None = None,
) -> tuple[list[Complaint], int]:
    statement = select(Complaint)
    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            Complaint.product_name.ilike(pattern)
            | Complaint.batch_lot_number.ilike(pattern)
            | Complaint.customer_name.ilike(pattern)
            | Complaint.complaint_number.ilike(pattern)
        )
    if status:
        statement = statement.where(Complaint.status == status)

    total = db.execute(
        select(func.count()).select_from(statement.subquery())
    ).scalar_one()
    rows = db.execute(
        statement.order_by(Complaint.created_at.desc(), Complaint.id.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return list(rows), total


def get_complaint(db: Session, complaint_id: int) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise ComplaintNotFoundError(f"Complaint {complaint_id} does not exist.")
    return complaint


def update_complaint(db: Session, complaint_id: int, payload: ComplaintUpdate) -> Complaint:
    complaint = get_complaint(db, complaint_id)
    # exclude_unset: only the fields the client actually sent are touched.
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(complaint, key, value)
    db.commit()
    db.refresh(complaint)
    return complaint


def delete_complaint(db: Session, complaint_id: int) -> None:
    complaint = get_complaint(db, complaint_id)
    db.delete(complaint)
    db.commit()
