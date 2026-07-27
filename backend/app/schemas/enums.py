"""Controlled vocabularies.

Values are lowercase snake_case so they are stable in the database and in JSON; the
frontend owns the human-readable labels.
"""

from enum import StrEnum


class ComplaintSource(StrEnum):
    CUSTOMER_EMAIL = "customer_email"
    DISTRIBUTOR = "distributor"
    HEALTHCARE_PROFESSIONAL = "healthcare_professional"
    PATIENT = "patient"
    REGULATORY_AUTHORITY = "regulatory_authority"
    SALES_REPRESENTATIVE = "sales_representative"
    INTERNAL = "internal"
    OTHER = "other"


class ComplaintType(StrEnum):
    PRODUCT_QUALITY_DEFECT = "product_quality_defect"
    PACKAGING_DEFECT = "packaging_defect"
    LABELLING_ERROR = "labelling_error"
    CONTAMINATION = "contamination"
    ADVERSE_EVENT = "adverse_event"
    LACK_OF_EFFICACY = "lack_of_efficacy"
    WRONG_PRODUCT_OR_STRENGTH = "wrong_product_or_strength"
    DOCUMENTATION = "documentation"
    SHIPPING_AND_DELIVERY = "shipping_and_delivery"
    OTHER = "other"


class Severity(StrEnum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ComplaintStatus(StrEnum):
    OPEN = "open"
    UNDER_INVESTIGATION = "under_investigation"
    CLOSED = "closed"


# Ordering used by the deterministic risk floor to take "the worse of the two" opinions.
RISK_ORDER: list[str] = [RiskLevel.UNKNOWN, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
SEVERITY_ORDER: list[str] = [Severity.UNKNOWN, Severity.MINOR, Severity.MAJOR, Severity.CRITICAL]
PRIORITY_ORDER: list[str] = [Priority.LOW, Priority.MEDIUM, Priority.HIGH, Priority.URGENT]


def max_by_order(order: list[str], *values: str | None) -> str:
    """Return the most serious of the given values according to `order`."""
    best = order[0]
    for value in values:
        if value in order and order.index(value) > order.index(best):
            best = value
    return best
