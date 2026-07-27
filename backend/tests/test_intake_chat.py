"""Conversational complaint-intake endpoint."""

from fastapi.testclient import TestClient


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
