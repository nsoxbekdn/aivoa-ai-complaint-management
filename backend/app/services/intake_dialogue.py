"""Deterministic conversation policy for reporter-facing complaint intake.

The LLM understands language, but this module decides what the assistant should do next.
Keeping those responsibilities separate prevents a rejected value from turning into a
repetitive "please answer again" loop.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime

from app.schemas.analysis import CompletenessAssessment
from app.schemas.intake import IntakeFieldCandidate
from app.services.completeness import HUMAN_LABELS

REPORTER_FACT_FIELDS = {
    "complaint_source",
    "customer_name",
    "customer_contact",
    "product_name",
    "product_strength_grade",
    "batch_lot_number",
    "manufacturing_date",
    "expiry_date",
    "quantity_affected",
    "quantity_unit",
    "complaint_type",
    "complaint_date",
    "complaint_details",
}

DATE_FIELDS = {"manufacturing_date", "expiry_date", "complaint_date"}

FIELD_LABELS = {
    **HUMAN_LABELS,
    "customer_name": "reporter name",
    "product_strength_grade": "strength or grade",
    "complaint_date": "date the problem was observed",
    "complaint_details": "complaint description",
}

FOLLOW_UP_QUESTIONS = {
    "complaint_source": (
        "How did you report this complaint—for example by email, through a distributor, "
        "as a patient, or as a healthcare professional?"
    ),
    "customer_name": "Who is reporting the complaint? Please share the person or organisation name.",
    "customer_contact": "What is the best email address or phone number for follow-up?",
    "product_name": "Which product is the complaint about?",
    "product_strength_grade": "What strength or grade is printed on the product?",
    "batch_lot_number": "What batch or lot number is printed on the bottle, carton, or blister?",
    "manufacturing_date": "What manufacturing date is printed on the product, if available?",
    "expiry_date": "What expiry date is printed on the product, if available?",
    "quantity_affected": "How many units are affected?",
    "quantity_unit": "What type of units are affected—for example bottles, tablets, vials, or packs?",
    "complaint_type": (
        "In your own words, is this mainly a product, packaging, labelling, safety, "
        "or delivery problem?"
    ),
    "complaint_date": "On what date was the problem first noticed or reported?",
    "complaint_details": "Could you describe exactly what was observed and what happened to the product?",
}

ANSWER_EXAMPLES = {
    "complaint_source": '"email", "distributor", or "patient"',
    "customer_name": '"Apollo Pharmacy" or the reporter’s name',
    "customer_contact": '"name@example.com" or a phone number',
    "product_name": '"ClearCough Syrup"',
    "product_strength_grade": '"200 mg/5 mL"',
    "batch_lot_number": '"CC26045"',
    "manufacturing_date": '"25 June 2025"',
    "expiry_date": '"30 June 2027"',
    "quantity_affected": '"5"',
    "quantity_unit": '"bottles"',
    "complaint_type": '"packaging problem"',
    "complaint_date": '"25 July 2026"',
    "complaint_details": '"five bottles leaked because their caps were loose"',
}

_LABEL_TO_FIELD = {label: field for field, label in HUMAN_LABELS.items()}
_UNAVAILABLE_RE = re.compile(
    r"^\s*(?:i\s+)?(?:do(?:n['’]?t|\s+not)\s+know|"
    r"(?:it\s+is\s+)?not\s+(?:available|printed|shown|provided|known)|"
    r"unknown|unavailable|n/?a|can(?:not|'t)\s+find\s+it|"
    r"i\s+have\s+no\s+idea|skip)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_ORDINAL_RE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_DAY_RE = re.compile(r"\b([0-3]?\d)\b")
_MONTHS = {
    name.lower(): number
    for number in range(1, 13)
    for name in (calendar.month_name[number], calendar.month_abbr[number])
}


def field_from_label(label: str) -> str | None:
    return _LABEL_TO_FIELD.get(label)


def question_for(field: str, *, retry_count: int = 0) -> str:
    base = FOLLOW_UP_QUESTIONS.get(
        field, f"Could you provide the {FIELD_LABELS.get(field, field.replace('_', ' '))}?"
    )
    if retry_count < 2:
        return base
    example = ANSWER_EXAMPLES.get(field)
    if not example:
        return base
    return f"{base} For example, you can reply {example}, or say “not available” if it is not shown."


def next_intake_question(
    completeness: CompletenessAssessment,
    unavailable_fields: set[str],
) -> tuple[str | None, str | None]:
    """Return the next field and question, skipping optional values the reporter cannot provide."""

    critical = [
        field_from_label(label)
        for label in completeness.missing_critical_fields
    ]
    optional = [
        field_from_label(label)
        for label in completeness.missing_optional_fields
        if label not in {"initial severity", "priority"}
    ]
    ordered = [field for field in [*critical, *optional] if field]
    available = [field for field in ordered if field not in unavailable_fields]
    if not available:
        return None, None
    field = available[0]
    return field, question_for(field)


def is_unavailable_answer(message: str) -> bool:
    return bool(_UNAVAILABLE_RE.fullmatch(message))


def may_be_unavailable_answer(message: str) -> bool:
    """Sanity gate for the model's ``unavailable`` intent.

    Marking a field unavailable is sticky — the assistant stops asking for it — so a wrong
    call here quietly loses a required value. A message carrying a concrete value ("6 bottles",
    "batch CC26045") is never a "cannot provide it", however the model labelled it. Phrasings
    the strict regex above cannot cover ("the carton doesn't show it anywhere") still pass.
    """
    return not re.search(r"\d", message)


# Canonical unit -> the spellings a reporter actually types. Mirrors QUANTITY_UNITS in the
# frontend's labels.ts, so a parsed unit always matches an option in the form's dropdown.
_UNIT_SPELLINGS = {
    "tablets": ("tablet", "tablets", "tabs", "tab"),
    "capsules": ("capsule", "capsules", "caps"),
    "bottles": ("bottle", "bottles"),
    "vials": ("vial", "vials"),
    "ampoules": ("ampoule", "ampoules", "ampule", "ampules", "amps"),
    "blisters": ("blister", "blisters", "strip", "strips"),
    "cartons": ("carton", "cartons", "box", "boxes"),
    "packs": ("pack", "packs", "packet", "packets"),
    "units": ("unit", "units", "piece", "pieces", "pcs"),
    "kg": ("kg", "kgs", "kilogram", "kilograms"),
    "litres": ("litre", "litres", "liter", "liters"),
}
_UNIT_BY_SPELLING = {
    spelling: canonical
    for canonical, spellings in _UNIT_SPELLINGS.items()
    for spelling in spellings
}
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100,
}
_NUMBER = rf"(\d+(?:\.\d+)?|{'|'.join(_NUMBER_WORDS)})"
_QUANTITY_WITH_UNIT_RE = re.compile(
    rf"\b{_NUMBER}\s*({'|'.join(sorted(_UNIT_BY_SPELLING, key=len, reverse=True))})\b",
    re.IGNORECASE,
)
_BARE_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


def _as_number(token: str) -> float:
    word = _NUMBER_WORDS.get(token.lower())
    return float(word) if word is not None else float(token)


def interpret_quantity_answer(
    message: str, *, pending_field: str | None = None
) -> tuple[float | None, str | None]:
    """Parse "6 bottles not 5" without asking the LLM. Returns (quantity, canonical unit).

    A quantity correction is the most common thing a reporter types and the easiest thing to
    read with a rule, so it should not depend on the provider being up. A number is only taken
    when a unit word follows it — which is what keeps "batch CC26045", "200 mg/5 mL" and
    "25 July 2026" out — or when the assistant explicitly asked for the quantity and the
    reporter answered with a single bare number.
    """
    match = _QUANTITY_WITH_UNIT_RE.search(message)
    if match:
        return _as_number(match.group(1)), _UNIT_BY_SPELLING[match.group(2).lower()]

    if pending_field == "quantity_affected":
        numbers = _BARE_NUMBER_RE.findall(message)
        if len(numbers) == 1:
            return float(numbers[0]), None

    return None, None


def _normalise_date_words(text: str) -> str:
    text = _ORDINAL_RE.sub(r"\1", text.lower())
    text = re.sub(r"[,]", " ", text)
    text = re.sub(r"\bof\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _month_in(text: str) -> tuple[int | None, re.Match[str] | None]:
    for word, number in sorted(_MONTHS.items(), key=lambda item: len(item[0]), reverse=True):
        match = re.search(rf"\b{re.escape(word)}\b", text)
        if match:
            return number, match
    return None, None


def _day_near_month(text: str, month_match: re.Match[str] | None) -> int | None:
    if not month_match:
        return None
    before = text[: month_match.start()]
    after = text[month_match.end() :]
    before_days = list(_DAY_RE.finditer(before))
    if before_days:
        return int(before_days[-1].group(1))
    after_day = _DAY_RE.search(after)
    return int(after_day.group(1)) if after_day else None


def _valid_day(day: int, month: int, year: int = 2000) -> bool:
    if not 1 <= month <= 12:
        return False
    return 1 <= day <= calendar.monthrange(year, month)[1]


def interpret_date_answer(
    field: str,
    message: str,
    existing_partial: str | None = None,
) -> tuple[date | None, IntakeFieldCandidate | None, str | None]:
    """Parse conversational dates without inventing omitted calendar information."""

    if field not in DATE_FIELDS:
        return None, None, None

    text = _normalise_date_words(message)
    year_match = _YEAR_RE.search(text)
    year = int(year_match.group(1)) if year_match else None

    if existing_partial and year and not _month_in(text)[0]:
        combined = f"{existing_partial} {year}"
        try:
            parsed = datetime.strptime(combined, "%d %B %Y").date()
        except ValueError:
            return (
                None,
                IntakeFieldCandidate(
                    field=field,
                    raw_value=message,
                    status="invalid",
                    reason="The supplied year does not form a valid date with the earlier answer.",
                ),
                existing_partial,
            )
        return (
            parsed,
            IntakeFieldCandidate(field=field, raw_value=message, status="accepted"),
            None,
        )

    # Numeric and ISO full dates are common enough to parse deterministically.
    for pattern, formats in (
        (r"\b\d{4}-\d{1,2}-\d{1,2}\b", ("%Y-%m-%d",)),
        (r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b", ("%d/%m/%Y", "%d-%m-%Y")),
    ):
        match = re.search(pattern, text)
        if not match:
            continue
        raw = match.group(0)
        for fmt in formats:
            try:
                parsed = datetime.strptime(raw, fmt).date()
                return (
                    parsed,
                    IntakeFieldCandidate(field=field, raw_value=message, status="accepted"),
                    None,
                )
            except ValueError:
                continue
        return (
            None,
            IntakeFieldCandidate(
                field=field,
                raw_value=message,
                status="invalid",
                reason="That is not a valid calendar date.",
            ),
            None,
        )

    month, month_match = _month_in(text)
    day = _day_near_month(text, month_match)
    if month is None or day is None:
        return None, None, existing_partial

    if not _valid_day(day, month, year or 2000):
        month_name = calendar.month_name[month]
        return (
            None,
            IntakeFieldCandidate(
                field=field,
                raw_value=message,
                status="invalid",
                reason=f"{month_name} does not have a day {day}.",
            ),
            None,
        )

    month_name = calendar.month_name[month]
    if year is None:
        partial = f"{day} {month_name}"
        return (
            None,
            IntakeFieldCandidate(
                field=field,
                raw_value=message,
                status="partial",
                reason=f"I understood {partial}, but the year is missing.",
            ),
            partial,
        )

    parsed = date(year, month, day)
    return (
        parsed,
        IntakeFieldCandidate(field=field, raw_value=message, status="accepted"),
        None,
    )


def issue_reply(candidate: IntakeFieldCandidate) -> str:
    label = FIELD_LABELS.get(candidate.field, candidate.field.replace("_", " "))
    if candidate.status == "partial":
        return f"{candidate.reason or f'The {label} is incomplete'} What year is printed?"
    if candidate.status == "invalid":
        return (
            f"I couldn’t record that as the {label}: "
            f"{candidate.reason or 'it is not a valid value'} Please check what is printed."
        )
    return (
        f"I’m not confident which value to record for the {label}. "
        "Could you say it another way or check the form beside the chat?"
    )
