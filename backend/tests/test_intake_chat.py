"""Conversational complaint-intake endpoint."""

from fastapi.testclient import TestClient

from app.llm.groq_client import LLMError


COMPLETE_BASE = {
    "complaint_source": "customer_email",
    "customer_name": "Apollo Pharmacy",
    "customer_contact": "qa@apollo.example",
    "product_name": "Amoxicillin Capsules",
    "product_strength_grade": "500 mg",
    "batch_lot_number": None,
    "manufacturing_date": "2026-03-01",
    "expiry_date": "2028-02-28",
    "quantity_affected": None,
    "quantity_unit": "capsules",
    "complaint_type": "product_quality_defect",
    "complaint_date": "2026-07-25",
    "complaint_details": "Discoloured capsules were found in a sealed bottle.",
    "initial_severity": "major",
    "priority": "high",
}


def test_intake_chat_applies_natural_language_correction(
    client: TestClient, monkeypatch
) -> None:
    def fake_turn(*args, **kwargs):
        return {
            "field_updates": {
                "batch_lot_number": "AMX240602",
                "quantity_affected": 48,
            },
            "clear_fields": [],
            "clarification_answer": None,
            "confirmation": False,
        }

    monkeypatch.setattr("app.api.routes.complaints.complete_json", fake_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "The batch number is AMX240602 and 48 capsules were affected.",
            "current_fields": COMPLETE_BASE,
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated_fields"]["batch_lot_number"] == "AMX240602"
    assert body["updated_fields"]["quantity_affected"] == 48
    assert set(body["changed_fields"]) == {"batch_lot_number", "quantity_affected"}
    assert body["ready_to_lodge"] is True
    assert "Got it" in body["assistant_message"]


def test_a_value_bearing_message_is_never_marked_unavailable(
    client: TestClient, monkeypatch
) -> None:
    """Observed live: asked for the reporter name, the reporter typed "6 bottles" and the
    model labelled the turn `unavailable`. Marking a field unavailable is sticky, so that
    silently stopped the assistant ever asking for the name again."""

    def fake_turn(*args, **kwargs):
        return {"intent": "unavailable", "field_updates": {}, "clear_fields": []}

    monkeypatch.setattr("app.api.routes.complaints.complete_json", fake_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "6 bottles",
            "current_fields": {**COMPLETE_BASE, "batch_lot_number": None},
            "history": [],
            "dialogue_state": {"pending_field": "batch_lot_number"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dialogue_state"]["unavailable_fields"] == []
    assert body["action"] != "acknowledge_unavailable"


def test_a_genuine_cannot_answer_is_still_honoured(client: TestClient, monkeypatch) -> None:
    def fake_turn(*args, **kwargs):
        return {"intent": "unavailable", "field_updates": {}, "clear_fields": []}

    monkeypatch.setattr("app.api.routes.complaints.complete_json", fake_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "the carton doesn't show it anywhere",
            "current_fields": {**COMPLETE_BASE, "batch_lot_number": None},
            "history": [],
            "dialogue_state": {"pending_field": "batch_lot_number"},
        },
    )

    assert response.status_code == 200
    assert response.json()["dialogue_state"]["unavailable_fields"] == ["batch_lot_number"]


def test_repeating_a_value_already_on_the_form_is_acknowledged(
    client: TestClient, monkeypatch
) -> None:
    """Re-sending a correction that already landed used to read as "I couldn't connect that
    answer to a form field", which makes a working assistant look broken."""

    def fake_turn(*args, **kwargs):
        return {"intent": "correct_information", "field_updates": {"quantity_affected": 6}}

    monkeypatch.setattr("app.api.routes.complaints.complete_json", fake_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "6 bottles not 5",
            "current_fields": {**COMPLETE_BASE, "quantity_affected": 6},
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["changed_fields"] == []
    assert body["action"] == "confirm_understanding"
    assert "already matches the form" in body["assistant_message"]


def test_provider_failure_keeps_the_conversation_alive(client: TestClient, monkeypatch) -> None:
    """A rate limit or a non-JSON reply used to 503 the turn: the reporter lost their message
    and got "could not understand that response", which blames them for a provider outage.
    The turn must still answer, keep the form untouched, and say what actually happened."""

    def fake_turn(*args, **kwargs):
        raise LLMError("AI provider unavailable (rate limited).")

    monkeypatch.setattr("app.api.routes.complaints.complete_json", fake_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "the caps looked loose on the outer ones",
            "current_fields": {**COMPLETE_BASE, "quantity_affected": 5},
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated_fields"]["quantity_affected"] == 5, "nothing may be invented"
    assert body["changed_fields"] == []
    assert "AI service did not respond" in body["assistant_message"]


def test_provider_failure_still_applies_a_quantity_correction(
    client: TestClient, monkeypatch
) -> None:
    """The original reported bug, with the provider down: "6 bottles not 5" is unambiguous to
    a rule, so it must not depend on the LLM answering."""

    def fake_turn(*args, **kwargs):
        raise LLMError("AI provider unavailable (rate limited).")

    monkeypatch.setattr("app.api.routes.complaints.complete_json", fake_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "6 bottles not 5",
            "current_fields": {
                **COMPLETE_BASE,
                "quantity_affected": 5,
                "quantity_unit": "bottles",
            },
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated_fields"]["quantity_affected"] == 6
    assert body["changed_fields"] == ["quantity_affected"]
    assert "corrected" in body["assistant_message"]


def test_provider_failure_still_parses_a_date_answer(client: TestClient, monkeypatch) -> None:
    """Date handling is rule-based, so it must survive the LLM being down."""

    def fake_turn(*args, **kwargs):
        raise LLMError("AI provider unavailable (rate limited).")

    monkeypatch.setattr("app.api.routes.complaints.complete_json", fake_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "12 June 2026",
            "current_fields": {**COMPLETE_BASE, "expiry_date": None},
            "history": [],
            "dialogue_state": {"pending_field": "expiry_date"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated_fields"]["expiry_date"] == "2026-06-12"
    assert body["changed_fields"] == ["expiry_date"]


def test_intake_chat_explains_a_term_without_changing_fields(
    client: TestClient, monkeypatch
) -> None:
    def fake_turn(*args, **kwargs):
        return {
            "field_updates": {},
            "clear_fields": [],
            "clarification_answer": (
                "A batch or lot number identifies the manufacturing run and is printed on the pack."
            ),
            "confirmation": False,
        }

    monkeypatch.setattr("app.api.routes.complaints.complete_json", fake_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "What is a batch number?",
            "current_fields": COMPLETE_BASE,
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["changed_fields"] == []
    assert "manufacturing run" in body["assistant_message"]
    assert "batch" in body["assistant_message"].lower()


def _date_question_base() -> dict:
    return {
        **COMPLETE_BASE,
        "batch_lot_number": "AMX240602",
        "manufacturing_date": None,
        "quantity_affected": 5,
    }


def _empty_turn(*args, **kwargs):
    return {
        "intent": "provide_information",
        "field_updates": {},
        "field_candidates": [],
        "clear_fields": [],
        "clarification_answer": None,
        "confirmation": False,
    }


def test_invalid_human_date_gets_a_specific_explanation(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr("app.api.routes.complaints.complete_json", _empty_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "manufactured on the 35th of June",
            "current_fields": _date_question_base(),
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "explain_invalid_value"
    assert body["updated_fields"]["manufacturing_date"] is None
    assert "does not have a day 35" in body["assistant_message"]
    assert body["dialogue_state"]["pending_field"] == "manufacturing_date"


def test_partial_date_is_remembered_and_completed_by_a_year(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr("app.api.routes.complaints.complete_json", _empty_turn)
    first = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "manufactured on 25th of June",
            "current_fields": _date_question_base(),
            "history": [],
        },
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["action"] == "clarify_partial_value"
    assert first_body["dialogue_state"]["partial_fields"]["manufacturing_date"] == "25 June"
    assert "What year" in first_body["assistant_message"]

    second = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "2025",
            "current_fields": first_body["updated_fields"],
            "dialogue_state": first_body["dialogue_state"],
            "history": [
                {"role": "user", "text": "manufactured on 25th of June"},
                {"role": "assistant", "text": first_body["assistant_message"]},
            ],
        },
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["updated_fields"]["manufacturing_date"] == "2025-06-25"
    assert "manufacturing_date" in second_body["changed_fields"]
    assert "25 June 2025" in second_body["assistant_message"]
    assert "manufacturing_date" not in second_body["dialogue_state"]["partial_fields"]


def test_unavailable_optional_answer_is_acknowledged_and_not_reasked(
    client: TestClient, monkeypatch
) -> None:
    def unavailable_turn(*args, **kwargs):
        return {
            **_empty_turn(),
            "intent": "unavailable",
        }

    monkeypatch.setattr("app.api.routes.complaints.complete_json", unavailable_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "it isn't printed",
            "current_fields": _date_question_base(),
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "acknowledge_unavailable"
    assert "manufacturing_date" in body["dialogue_state"]["unavailable_fields"]
    assert "won’t keep asking" in body["assistant_message"]
    assert body["dialogue_state"]["pending_field"] != "manufacturing_date"


def test_existing_value_correction_is_confirmed_naturally(
    client: TestClient, monkeypatch
) -> None:
    def correction_turn(*args, **kwargs):
        return {
            **_empty_turn(),
            "intent": "correct_information",
            "field_updates": {"quantity_affected": 6},
            "field_candidates": [
                {
                    "field": "quantity_affected",
                    "raw_value": "actually six bottles",
                    "status": "accepted",
                    "reason": None,
                }
            ],
        }

    monkeypatch.setattr("app.api.routes.complaints.complete_json", correction_turn)
    fields = _date_question_base()
    fields["manufacturing_date"] = "2025-06-25"
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "No wait, actually six bottles",
            "current_fields": fields,
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "confirm_correction"
    assert body["updated_fields"]["quantity_affected"] == 6
    assert "corrected affected quantity from 5" in body["assistant_message"]
    assert "affected quantity as 6" in body["assistant_message"]


def test_repeated_unclear_answer_changes_the_question_and_gives_an_example(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr("app.api.routes.complaints.complete_json", _empty_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "uh the thing on the side",
            "current_fields": _date_question_base(),
            "history": [],
            "dialogue_state": {
                "pending_field": "manufacturing_date",
                "partial_fields": {},
                "unavailable_fields": [],
                "question_history": [],
                "retry_counts": {"manufacturing_date": 1},
                "last_action": "clarify_ambiguous_value",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "clarify_ambiguous_value"
    assert "For example" in body["assistant_message"]
    assert "25 June 2025" in body["assistant_message"]


def test_form_question_is_answered_without_treating_it_as_complaint_data(
    client: TestClient, monkeypatch
) -> None:
    def question_turn(*args, **kwargs):
        return {
            **_empty_turn(),
            "intent": "ask_question",
            "clarification_answer": (
                "The manufacturing date helps QA trace the production records for the affected batch."
            ),
        }

    monkeypatch.setattr("app.api.routes.complaints.complete_json", question_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "Why do you need the manufacturing date?",
            "current_fields": _date_question_base(),
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "answer_question"
    assert body["changed_fields"] == []
    assert "trace the production records" in body["assistant_message"]
    assert "What manufacturing date" in body["assistant_message"]


def test_casual_remark_is_acknowledged_instead_of_being_treated_as_a_failed_answer(
    client: TestClient, monkeypatch
) -> None:
    """A greeting or an apology used to fall through to "I couldn't connect that answer",
    which is what made the assistant feel like a form rather than a conversation."""

    def smalltalk_turn(*args, **kwargs):
        return {**_empty_turn(), "intent": "unrelated"}

    monkeypatch.setattr("app.api.routes.complaints.complete_json", smalltalk_turn)
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "sorry, this is my first time reporting one of these",
            "current_fields": _date_question_base(),
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "acknowledge_smalltalk"
    assert body["changed_fields"] == []
    assert "couldn’t confidently connect" not in body["assistant_message"]
    # The point of acknowledging it is that the conversation still moves forward.
    assert body["dialogue_state"]["pending_field"] == "manufacturing_date"


def test_the_reply_is_phrased_naturally_when_the_model_is_available(
    client: TestClient, monkeypatch
) -> None:
    def correction_turn(*args, **kwargs):
        return {**_empty_turn(), "field_updates": {"manufacturing_date": "2026-03-02"}}

    natural = "Thanks, I've noted that down. What expiry date is printed on the carton?"
    monkeypatch.setattr("app.api.routes.complaints.complete_json", correction_turn)
    monkeypatch.setattr(
        "app.services.intake_reply.complete_text", lambda *a, **k: f"**{natural}**"
    )
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "manufactured on 2 March 2026",
            "current_fields": _date_question_base(),
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    # The phrasing model chose the words; the deterministic layer still owns the record.
    assert body["assistant_message"] == natural
    assert body["updated_fields"]["manufacturing_date"] == "2026-03-02"


def test_a_reply_that_invents_a_number_is_thrown_away(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr("app.api.routes.complaints.complete_json", _empty_turn)
    monkeypatch.setattr(
        "app.services.intake_reply.complete_text",
        lambda *a, **k: "Noted — batch CC99999 is recorded. What manufacturing date is printed?",
    )
    response = client.post(
        "/api/complaints/intake/chat",
        json={
            "message": "not sure what else you need",
            "current_fields": _date_question_base(),
            "history": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "CC99999" not in body["assistant_message"]
