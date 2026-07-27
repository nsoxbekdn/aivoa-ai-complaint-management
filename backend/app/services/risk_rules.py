"""Deterministic risk heuristic.

Two jobs:
1. Safety net — if Groq is unreachable the API still returns a usable, explainable triage.
2. Floor — the final risk is never *lower* than this rule-based opinion, so a model that
   under-reacts to the word "sterile" cannot silently downgrade a critical complaint.

These are preliminary heuristics for triage only, not a regulatory classification.
"""

from __future__ import annotations

import re

from app.schemas.analysis import ExtractedComplaintFields, RiskAssessment
from app.schemas.enums import (
    PRIORITY_ORDER,
    RISK_ORDER,
    SEVERITY_ORDER,
    Priority,
    RiskLevel,
    Severity,
    max_by_order,
)

# Keyword → risk level. Ordered most serious first; the first match at each level wins.
CRITICAL_PATTERNS: dict[str, str] = {
    r"\bsteril\w*": "possible sterility concern",
    r"\bcontaminat\w*": "possible contamination",
    r"\bparticulate|\bforeign (matter|particle)": "particulate / foreign matter reported",
    r"\bwrong (product|drug|medicine|strength)|\bmix[- ]?up": "possible product mix-up",
    r"\bincorrect strength|\bwrong strength": "possible incorrect strength",
    r"\bhospitali[sz]ed|\bdeath|\bfatal|\blife[- ]threatening": "serious adverse outcome reported",
    r"\banaphyla\w*|\bseizure|\bsevere reaction": "serious adverse reaction reported",
    r"\binjectab\w*|\bvial|\bampoule|\bIV\b": "parenteral product involved",
}

HIGH_PATTERNS: dict[str, str] = {
    r"\badverse (event|reaction)|\bside[- ]effect|\brash|\bnausea|\bvomit\w*": "adverse reaction reported",
    r"\bwrong label|\bincorrect label|\bmislabel\w*|\blabel(ling)? error": "labelling issue",
    r"\bbroken seal|\btamper\w*|\bseal (is )?broken": "container closure integrity concern",
    r"\bno effect|\black of effect|\bnot working|\bineffective": "possible lack of efficacy",
    r"\bmultiple (batches|lots)|\brepeated\w*|\brecurring": "repeat / multi-batch issue",
    r"\bleak\w*|\bleaking|\bspill\w*": "container leakage",
    r"\bdiscolo(u)?r\w*|\bcolour change|\bcolor change": "appearance / stability concern",
    r"\bmissing (tablets|capsules|units)|\bunderfill\w*|\bshort fill": "content shortage",
    r"\bodou?r|\bsmell": "unusual odour reported",
}

MEDIUM_PATTERNS: dict[str, str] = {
    r"\bdamaged|\bbroken|\bcracked|\bchipped|\bcrumbl\w*": "physical damage reported",
    # Only *damaged* secondary packaging is a quality signal; the word "carton" alone is not.
    r"\bcrushed|\btorn|\bdented|\bsoaked|\bwet\b": "secondary packaging damage",
    r"\bmoist\w*|\bhumid\w*|\bcold chain|\btemperature excursion": "storage condition concern",
}

LOW_PATTERNS: dict[str, str] = {
    r"\bcosmetic|\bprint quality|\bsmudg\w*|\bscratch": "cosmetic issue",
    r"\bdelivery|\bshipment delay|\binvoice|\bdocumentation|\bcertificate of analysis": "service / documentation issue",
}

PATIENT_SAFETY_PATTERNS = (
    r"\bpatient|\badverse|\bhospitali[sz]ed|\bdeath|\bfatal|\breaction|\bsteril\w*|\bcontaminat\w*"
)

# Complaint types that carry their own floor regardless of wording.
TYPE_FLOOR: dict[str, str] = {
    "contamination": RiskLevel.CRITICAL,
    "adverse_event": RiskLevel.CRITICAL,
    "wrong_product_or_strength": RiskLevel.CRITICAL,
    "labelling_error": RiskLevel.HIGH,
    "lack_of_efficacy": RiskLevel.HIGH,
    "product_quality_defect": RiskLevel.MEDIUM,
    "packaging_defect": RiskLevel.MEDIUM,
    "shipping_and_delivery": RiskLevel.LOW,
    "documentation": RiskLevel.LOW,
}

RISK_TO_SEVERITY: dict[str, str] = {
    RiskLevel.CRITICAL: Severity.CRITICAL,
    RiskLevel.HIGH: Severity.MAJOR,
    RiskLevel.MEDIUM: Severity.MAJOR,
    RiskLevel.LOW: Severity.MINOR,
    RiskLevel.UNKNOWN: Severity.UNKNOWN,
}

RISK_TO_PRIORITY: dict[str, str] = {
    RiskLevel.CRITICAL: Priority.URGENT,
    RiskLevel.HIGH: Priority.HIGH,
    RiskLevel.MEDIUM: Priority.MEDIUM,
    RiskLevel.LOW: Priority.LOW,
    RiskLevel.UNKNOWN: Priority.MEDIUM,
}


def _matches(text: str, patterns: dict[str, str]) -> list[str]:
    return [
        reason
        for pattern, reason in patterns.items()
        if _has_non_negated_match(text, pattern)
    ]


_NEGATION_PREFIX = re.compile(
    r"(?:\bno\b|\bnot\b|\bwithout\b|\bnever\b|\bnone\b|\bdidn['â€™]?t\b|\bdid not\b)"
    r"(?:\s+\w+){0,4}\s*$",
    re.IGNORECASE,
)


def _has_non_negated_match(text: str, pattern: str) -> bool:
    """Return true only when at least one nearby match is not explicitly negated."""
    for match in re.finditer(pattern, text, re.IGNORECASE):
        prefix = text[max(0, match.start() - 60):match.start()]
        if not _NEGATION_PREFIX.search(prefix):
            return True
    return False


def heuristic_risk(text: str, fields: ExtractedComplaintFields) -> RiskAssessment:
    """Keyword + complaint-type triage. Explainable, offline, always available."""
    haystack = " ".join(filter(None, [text, fields.complaint_details or ""]))

    level = RiskLevel.UNKNOWN
    reasons: list[str] = []
    for candidate, patterns in (
        (RiskLevel.CRITICAL, CRITICAL_PATTERNS),
        (RiskLevel.HIGH, HIGH_PATTERNS),
        (RiskLevel.MEDIUM, MEDIUM_PATTERNS),
        (RiskLevel.LOW, LOW_PATTERNS),
    ):
        hits = _matches(haystack, patterns)
        if hits:
            reasons.extend(hits)
            level = max_by_order(RISK_ORDER, level, candidate)

    if fields.complaint_type:
        type_floor = TYPE_FLOOR.get(fields.complaint_type)
        if type_floor:
            level = max_by_order(RISK_ORDER, level, type_floor)
            reasons.append(f"complaint type '{fields.complaint_type.replace('_', ' ')}'")

    if level == RiskLevel.UNKNOWN:
        level = RiskLevel.MEDIUM
        reasons.append("no specific risk indicator matched; defaulted to medium pending review")

    rationale = "Rule-based triage matched: " + "; ".join(dict.fromkeys(reasons)) + "."
    return RiskAssessment(
        risk_level=level,
        severity=RISK_TO_SEVERITY[level],
        priority=RISK_TO_PRIORITY[level],
        patient_safety_concern=_has_non_negated_match(haystack, PATIENT_SAFETY_PATTERNS),
        product_quality_concern=level != RiskLevel.LOW,
        rationale=rationale,
        confidence=0.4,  # a keyword rule is a hint, not a judgement
    )


def merge_with_floor(model: RiskAssessment, floor: RiskAssessment) -> RiskAssessment:
    """Keep the model's reasoning but never let it rate below the deterministic floor."""
    raised = RISK_ORDER.index(floor.risk_level) > RISK_ORDER.index(model.risk_level)
    rationale = model.rationale.strip()
    if raised:
        rationale = (
            f"{rationale} [Raised from '{model.risk_level}' to '{floor.risk_level}' by the "
            f"deterministic safety rule: {floor.rationale}]"
        ).strip()
    return RiskAssessment(
        risk_level=max_by_order(RISK_ORDER, model.risk_level, floor.risk_level),
        severity=max_by_order(SEVERITY_ORDER, model.severity, floor.severity),
        priority=max_by_order(PRIORITY_ORDER, model.priority, floor.priority),
        patient_safety_concern=model.patient_safety_concern or floor.patient_safety_concern,
        product_quality_concern=model.product_quality_concern or floor.product_quality_concern,
        rationale=rationale,
        confidence=model.confidence,
    )
