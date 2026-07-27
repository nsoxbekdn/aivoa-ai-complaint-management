from datetime import date

from fastapi.testclient import TestClient


def test_create_returns_sequential_complaint_numbers(
    client: TestClient, valid_complaint_payload: dict
) -> None:
    first = client.post("/api/complaints", json=valid_complaint_payload)
    second = client.post("/api/complaints", json=valid_complaint_payload)

    assert first.status_code == 201
    year = date.today().year
    assert first.json()["complaint_number"] == f"CC-{year}-0001"
    assert second.json()["complaint_number"] == f"CC-{year}-0002"


def test_create_rejects_missing_required_fields(client: TestClient) -> None:
    response = client.post("/api/complaints", json={"customer_name": "Someone"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert {detail["field"] for detail in body["error"]["details"]} >= {
        "complaint_source",
        "product_name",
        "complaint_type",
        "complaint_date",
        "complaint_details",
    }


def test_create_rejects_future_complaint_date(
    client: TestClient, valid_complaint_payload: dict
) -> None:
    payload = valid_complaint_payload | {"complaint_date": "2099-01-01"}

    response = client.post("/api/complaints", json=payload)

    assert response.status_code == 422


def test_create_rejects_expiry_before_manufacturing(
    client: TestClient, valid_complaint_payload: dict
) -> None:
    payload = valid_complaint_payload | {
        "manufacturing_date": "2026-01-01",
        "expiry_date": "2025-01-01",
    }

    response = client.post("/api/complaints", json=payload)

    assert response.status_code == 422


def test_persisted_json_columns_round_trip(
    client: TestClient, valid_complaint_payload: dict
) -> None:
    payload = valid_complaint_payload | {
        "missing_fields": ["quantity affected"],
        "root_cause_recommendations": ["Compression force too high"],
        "initial_investigation_steps": ["Inspect retained samples"],
        "capa_recommendations": ["Re-qualify the line"],
        "duplicate_candidates": [
            {
                "complaint_id": 99,
                "complaint_number": "CC-2026-0099",
                "product_name": "Amoxinova",
                "batch_lot_number": "AMX-24118",
                "complaint_type": "product_quality_defect",
                "similarity": 0.91,
                "reason": "same batch",
            }
        ],
        "intake_transcript": [
            {"role": "assistant", "text": "What is the batch number?"},
            {"role": "user", "text": "AMX-24118"},
        ],
        "analysis_warnings": ["OCR used — verify extracted details."],
        "source_documents": [
            {
                "filename": "complaint.png",
                "media_type": "image/png",
                "extraction_method": "groq_vision",
                "text": "Complaint text",
                "page_count": 1,
                "ocr_used": True,
            }
        ],
        "risk_level": "medium",
        "risk_confidence": 0.82,
        "patient_safety_concern": False,
        "product_quality_concern": True,
        "completeness_score": 82,
    }

    created = client.post("/api/complaints", json=payload).json()
    fetched = client.get(f"/api/complaints/{created['id']}").json()

    assert fetched["root_cause_recommendations"] == ["Compression force too high"]
    assert fetched["initial_investigation_steps"] == ["Inspect retained samples"]
    assert fetched["duplicate_candidates"][0]["complaint_number"] == "CC-2026-0099"
    assert fetched["intake_transcript"][1]["text"] == "AMX-24118"
    assert fetched["risk_confidence"] == 0.82
    assert fetched["missing_fields"] == ["quantity affected"]
    assert fetched["completeness_score"] == 82
    assert fetched["analysis_warnings"][0].startswith("OCR used")
    assert fetched["source_documents"][0]["filename"] == "complaint.png"


def test_list_paginates_and_searches(client: TestClient, valid_complaint_payload: dict) -> None:
    client.post("/api/complaints", json=valid_complaint_payload)
    client.post("/api/complaints", json=valid_complaint_payload | {"product_name": "Cardiostat 10 mg"})

    listing = client.get("/api/complaints", params={"limit": 1}).json()
    assert listing["total"] == 2
    assert len(listing["items"]) == 1

    search = client.get("/api/complaints", params={"search": "Cardiostat"}).json()
    assert search["total"] == 1
    assert search["items"][0]["product_name"] == "Cardiostat 10 mg"


def test_update_changes_only_sent_fields(client: TestClient, valid_complaint_payload: dict) -> None:
    created = client.post("/api/complaints", json=valid_complaint_payload).json()

    updated = client.put(
        f"/api/complaints/{created['id']}",
        json={"priority": "urgent", "status": "under_investigation"},
    ).json()

    assert updated["priority"] == "urgent"
    assert updated["status"] == "under_investigation"
    assert updated["product_name"] == valid_complaint_payload["product_name"]


def test_delete_then_get_returns_404(client: TestClient, valid_complaint_payload: dict) -> None:
    created = client.post("/api/complaints", json=valid_complaint_payload).json()

    assert client.delete(f"/api/complaints/{created['id']}").status_code == 204
    missing = client.get(f"/api/complaints/{created['id']}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
