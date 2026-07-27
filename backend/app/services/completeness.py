"""Deterministic completeness scoring.

Plain Python on purpose: an intake officer must be able to predict the score, and the score
must not change between two runs of the same complaint. The LLM is only used afterwards to
phrase the follow-up questions.
"""

from __future__ import annotations

from app.schemas.analysis import CompletenessAssessment, ExtractedComplaintFields

# Fields an intake record cannot realistically be worked without.
CRITICAL_FIELDS: list[str] = [
    "complaint_source",
    "customer_name",
    "product_name",
    "batch_lot_number",
    "complaint_date",
    "complaint_details",
]

# Useful, but their absence does not block the investigation from starting.
OPTIONAL_FIELDS: list[str] = [
    "customer_contact",
    "product_strength_grade",
    "manufacturing_date",
    "expiry_date",
    "quantity_affected",
    "quantity_unit",
    "complaint_type",
    "initial_severity",
    "priority",
]

# For these complaint types "how much product is affected" drives the recall/scope decision,
# so it is promoted from optional to critical.
QUANTITY_CRITICAL_TYPES = {
    "product_quality_defect",
    "packaging_defect",
    "contamination",
    "wrong_product_or_strength",
    "labelling_error",
}

CRITICAL_WEIGHT = 0.7  # critical coverage dominates the score
OPTIONAL_WEIGHT = 0.3

HUMAN_LABELS: dict[str, str] = {
    "complaint_source": "complaint source",
    "customer_name": "customer name",
    "customer_contact": "customer contact",
    "product_name": "product name",
    "product_strength_grade": "product strength / grade",
    "batch_lot_number": "batch / lot number",
    "manufacturing_date": "manufacturing date",
    "expiry_date": "expiry date",
    "quantity_affected": "quantity affected",
    "quantity_unit": "quantity unit",
    "complaint_type": "complaint type",
    "complaint_date": "complaint date",
    "complaint_details": "complaint details",
    "initial_severity": "initial severity",
    "priority": "priority",
}

# Fallback questions used when the LLM is unavailable, so the panel is never empty.
_FALLBACK_QUESTIONS: dict[str, str] = {
    "batch_lot_number": "What is the batch / lot number printed on the pack?",
    "quantity_affected": "How many units are affected, and how many were received in total?",
    "complaint_date": "On what date was the problem first observed?",
    "customer_contact": "What is the best email or phone number to reach you on?",
    "customer_name": "Who is reporting this complaint (name and organisation)?",
    "product_name": "Which product does this complaint refer to?",
    "expiry_date": "What is the expiry date shown on the pack?",
    "manufacturing_date": "What is the manufacturing date shown on the pack?",
    "product_strength_grade": "What strength or grade of the product is affected?",
    "complaint_source": "How did this complaint reach us (email, distributor, sales rep)?",
    "complaint_details": "Could you describe exactly what was observed?",
}

# Extra prompts that depend on the kind of complaint, not on a missing form field.
_TYPE_QUESTIONS: dict[str, list[str]] = {
    "adverse_event": [
        "What symptoms did the patient experience, and how serious were they?",
        "What was the patient outcome, and was medical attention required?",
        "How was the product being used when the reaction occurred?",
    ],
    "contamination": [
        "Is a retained sample of the affected unit available for testing?",
        "How was the product stored and transported before the issue was noticed?",
    ],
    "product_quality_defect": [
        "Are photographs of the defect available?",
        "How was the product stored before the defect was noticed?",
    ],
    "packaging_defect": [
        "Are photographs of the damaged packaging available?",
        "Was the outer shipping carton also damaged?",
    ],
}


def _is_present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def critical_fields_for(fields: ExtractedComplaintFields) -> list[str]:
    """Critical list, adjusted for complaint type."""
    critical = list(CRITICAL_FIELDS)
    if fields.complaint_type and fields.complaint_type in QUANTITY_CRITICAL_TYPES:
        critical.append("quantity_affected")
    return critical


def assess_completeness(fields: ExtractedComplaintFields) -> CompletenessAssessment:
    """Score 0-100 and list what is missing."""
    critical = critical_fields_for(fields)
    optional = [name for name in OPTIONAL_FIELDS if name not in critical]

    missing_critical = [name for name in critical if not _is_present(getattr(fields, name))]
    missing_optional = [name for name in optional if not _is_present(getattr(fields, name))]

    critical_ratio = (len(critical) - len(missing_critical)) / len(critical)
    optional_ratio = (len(optional) - len(missing_optional)) / len(optional) if optional else 1.0
    score = round((critical_ratio * CRITICAL_WEIGHT + optional_ratio * OPTIONAL_WEIGHT) * 100)

    return CompletenessAssessment(
        score=score,
        is_complete=not missing_critical,
        missing_critical_fields=[HUMAN_LABELS.get(name, name) for name in missing_critical],
        missing_optional_fields=[HUMAN_LABELS.get(name, name) for name in missing_optional],
        follow_up_questions=fallback_questions(fields, missing_critical + missing_optional),
    )


def fallback_questions(fields: ExtractedComplaintFields, missing: list[str]) -> list[str]:
    """Deterministic follow-up questions, used when the LLM cannot be reached."""
    # Type-specific questions first: "was the patient hospitalised?" matters more than
    # "what is the expiry date?", and the list is capped at six.
    questions = list(_TYPE_QUESTIONS.get(fields.complaint_type, [])) if fields.complaint_type else []
    questions += [_FALLBACK_QUESTIONS[name] for name in missing if name in _FALLBACK_QUESTIONS]
    return questions[:6]
