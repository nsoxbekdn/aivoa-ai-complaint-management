"""Possible-duplicate detection.

Deliberately simple: a SQL pre-filter (same batch, same product, or same complaint type)
followed by `difflib.SequenceMatcher` on the normalised complaint text. No vector database —
the candidate set is tiny and the reviewer, not the system, decides what a duplicate is.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.schemas.analysis import DuplicateCandidate, ExtractedComplaintFields

CANDIDATE_LIMIT = 50
REPORT_THRESHOLD = 0.45  # below this the "match" is noise
_NON_WORD = re.compile(r"[^a-z0-9 ]+")
# SequenceMatcher is O(n*m). Against 50 stored complaints an uncapped incoming text turns
# this into minutes of blocking CPU (a 1 MB paste measured at 91s), so both sides are
# compared on their opening section only — which is where a duplicate declares itself.
_COMPARE_CHARS = 4_000


def _normalise(text: str | None) -> str:
    return _NON_WORD.sub(" ", (text or "")[:_COMPARE_CHARS].lower()).strip()


def find_possible_duplicates(
    db: Session, fields: ExtractedComplaintFields, complaint_text: str
) -> list[DuplicateCandidate]:
    """Return possible matches with a similarity score — never a verdict."""
    filters = []
    if fields.batch_lot_number:
        filters.append(Complaint.batch_lot_number.ilike(fields.batch_lot_number.strip()))
    if fields.product_name:
        filters.append(Complaint.product_name.ilike(f"%{fields.product_name.strip()}%"))
    if fields.complaint_type:
        filters.append(Complaint.complaint_type == fields.complaint_type)
    if not filters:
        return []

    rows = db.execute(select(Complaint).where(or_(*filters)).limit(CANDIDATE_LIMIT)).scalars().all()
    incoming = _normalise(complaint_text or fields.complaint_details)

    candidates: list[DuplicateCandidate] = []
    for row in rows:
        existing = _normalise(row.complaint_details or row.original_text)
        text_similarity = SequenceMatcher(None, incoming, existing).ratio() if incoming and existing else 0.0

        reasons: list[str] = []
        score = text_similarity * 0.5
        if fields.batch_lot_number and row.batch_lot_number:
            if fields.batch_lot_number.strip().lower() == row.batch_lot_number.strip().lower():
                score += 0.3
                reasons.append("same batch number")
        if fields.product_name and row.product_name:
            if fields.product_name.strip().lower() in row.product_name.strip().lower():
                score += 0.1
                reasons.append("same product")
        if fields.complaint_type and row.complaint_type == fields.complaint_type:
            score += 0.1
            reasons.append("same complaint type")
        if text_similarity > 0.6:
            reasons.append(f"complaint text {round(text_similarity * 100)}% similar")

        score = min(score, 1.0)
        if score >= REPORT_THRESHOLD and reasons:
            candidates.append(
                DuplicateCandidate(
                    complaint_id=row.id,
                    complaint_number=row.complaint_number,
                    product_name=row.product_name,
                    batch_lot_number=row.batch_lot_number,
                    complaint_type=row.complaint_type,
                    similarity=round(score, 2),
                    reason=", ".join(reasons),
                )
            )

    candidates.sort(key=lambda candidate: candidate.similarity, reverse=True)
    return candidates[:5]
