"""Unit tests for the deterministic parts: completeness, risk rules, JSON repair, schemas."""

import pytest

from app.llm.json_utils import JsonParseError, parse_json_object
from app.schemas.analysis import ExtractedComplaintFields, RiskAssessment
from app.services.completeness import assess_completeness
from app.services.intake_dialogue import interpret_quantity_answer
from app.services.risk_rules import heuristic_risk, merge_with_floor

# --- completeness ---------------------------------------------------------------------


def test_empty_complaint_scores_zero_and_is_incomplete() -> None:
    result = assess_completeness(ExtractedComplaintFields())

    assert result.score == 0
    assert result.is_complete is False
    assert "batch / lot number" in result.missing_critical_fields


def test_full_complaint_is_complete_and_scores_high() -> None:
    fields = ExtractedComplaintFields(
        complaint_source="customer_email",
        customer_name="Meridian Pharmacy Group",
        customer_contact="quality@meridianpharmacy.example",
        product_name="Amoxinova 500 mg Capsules",
        product_strength_grade="500 mg",
        batch_lot_number="AMX-24118",
        manufacturing_date="2025-11-02",
        expiry_date="2027-10-31",
        quantity_affected=12,
        quantity_unit="capsules",
        complaint_type="product_quality_defect",
        complaint_date="2026-06-14",
        complaint_details="Cracked capsules with powder leakage.",
        initial_severity="major",
        priority="high",
    )

    result = assess_completeness(fields)

    assert result.is_complete is True
    assert result.score == 100
    assert result.missing_critical_fields == []


def test_quantity_is_critical_for_defect_complaints_only() -> None:
    defect = ExtractedComplaintFields(complaint_type="product_quality_defect")
    service = ExtractedComplaintFields(complaint_type="shipping_and_delivery")

    assert "quantity affected" in assess_completeness(defect).missing_critical_fields
    assert "quantity affected" in assess_completeness(service).missing_optional_fields


def test_adverse_event_gets_domain_specific_follow_up_questions() -> None:
    fields = ExtractedComplaintFields(complaint_type="adverse_event")

    questions = " ".join(assess_completeness(fields).follow_up_questions).lower()

    assert "patient" in questions


# --- risk heuristic -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Particulate matter was seen floating in the injectable vial.", "critical"),
        ("The patient was hospitalised after taking the tablet.", "critical"),
        ("The label shows the wrong strength on the carton.", "critical"),
        ("The bottle was leaking during transport.", "high"),
        ("The outer shipping carton was damaged.", "medium"),
        ("The print on the carton is slightly smudged.", "low"),
    ],
)
def test_heuristic_risk_levels(text: str, expected: str) -> None:
    assessment = heuristic_risk(text, ExtractedComplaintFields())

    assert assessment.risk_level == expected
    assert assessment.rationale  # always explainable


def test_heuristic_defaults_to_medium_when_nothing_matches() -> None:
    assessment = heuristic_risk("The courier arrived at 9am.", ExtractedComplaintFields())

    assert assessment.risk_level == "medium"


def test_negated_adverse_event_and_smell_do_not_trigger_risk_flags() -> None:
    assessment = heuristic_risk(
        "No patient injury occurred. There was no adverse event and no unusual smell.",
        ExtractedComplaintFields(),
    )

    assert assessment.patient_safety_concern is False
    assert "adverse reaction reported" not in assessment.rationale
    assert "unusual odour reported" not in assessment.rationale


def test_positive_adverse_event_still_triggers_patient_safety() -> None:
    assessment = heuristic_risk(
        "The patient experienced an adverse reaction and required treatment.",
        ExtractedComplaintFields(),
    )

    assert assessment.patient_safety_concern is True
    assert assessment.risk_level == "high"


def test_floor_raises_but_never_lowers_the_model_rating() -> None:
    model_view = RiskAssessment(risk_level="low", severity="minor", priority="low", rationale="Looks minor.")
    floor = heuristic_risk("Possible contamination of the sterile vial.", ExtractedComplaintFields())

    merged = merge_with_floor(model_view, floor)

    assert merged.risk_level == "critical"
    assert "Raised from" in merged.rationale


def test_floor_does_not_downgrade_a_higher_model_rating() -> None:
    model_view = RiskAssessment(risk_level="critical", severity="critical", priority="urgent", rationale="Serious.")
    floor = heuristic_risk("The print on the carton is smudged.", ExtractedComplaintFields())

    assert merge_with_floor(model_view, floor).risk_level == "critical"


# --- JSON handling --------------------------------------------------------------------


def test_parse_json_object_strips_fences_and_prose() -> None:
    raw = 'Here is the JSON you asked for:\n```json\n{"summary": "ok"}\n```\nHope that helps!'

    assert parse_json_object(raw) == {"summary": "ok"}


def test_parse_json_object_repairs_trailing_comma() -> None:
    assert parse_json_object('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}


def test_parse_json_object_raises_on_garbage() -> None:
    with pytest.raises(JsonParseError):
        parse_json_object("no json here at all")


# --- schema hardening -----------------------------------------------------------------


def test_nullish_strings_become_none_instead_of_fake_values() -> None:
    fields = ExtractedComplaintFields.model_validate(
        {"batch_lot_number": "N/A", "customer_name": "unknown", "quantity_affected": "not specified"}
    )

    assert fields.batch_lot_number is None
    assert fields.customer_name is None
    assert fields.quantity_affected is None


def test_unparseable_date_is_dropped_not_guessed() -> None:
    fields = ExtractedComplaintFields.model_validate({"complaint_date": "sometime last month"})

    assert fields.complaint_date is None


def test_alternative_date_formats_are_accepted() -> None:
    fields = ExtractedComplaintFields.model_validate({"complaint_date": "14 June 2026"})

    assert fields.complaint_date.isoformat() == "2026-06-14"


def test_unknown_enum_value_becomes_none() -> None:
    fields = ExtractedComplaintFields.model_validate({"complaint_type": "aliens_took_it"})

    assert fields.complaint_type is None


def test_quantity_is_extracted_from_a_noisy_string() -> None:
    fields = ExtractedComplaintFields.model_validate({"quantity_affected": "about 12 capsules"})

    assert fields.quantity_affected == 12.0


# --- deterministic quantity parsing ---------------------------------------------------


@pytest.mark.parametrize(
    "message, expected",
    [
        ("6 bottles not 5", (6.0, "bottles")),
        ("6 bottles, not 5", (6.0, "bottles")),
        ("six bottles", (6.0, "bottles")),
        ("actually 12 vials were affected", (12.0, "vials")),
        ("2 strips", (2.0, "blisters")),
        ("1.5 kg", (1.5, "kg")),
        # A number with no unit beside it is not a quantity — these are the values the rule
        # must refuse, or it would overwrite the batch, the strength, or a date.
        ("the batch is CC26045", (None, None)),
        ("200 mg/5 mL", (None, None)),
        ("25 July 2026", (None, None)),
        ("no idea", (None, None)),
    ],
)
def test_quantity_is_parsed_only_when_a_unit_follows_the_number(
    message: str, expected: tuple[float | None, str | None]
) -> None:
    assert interpret_quantity_answer(message) == expected


def test_a_bare_number_counts_only_when_the_quantity_was_asked_for() -> None:
    assert interpret_quantity_answer("6") == (None, None)
    assert interpret_quantity_answer("6", pending_field="quantity_affected") == (6.0, None)
    # Two numbers is not an answer to "how many?" — leave it to the model.
    assert interpret_quantity_answer("6 or 7", pending_field="quantity_affected") == (None, None)
