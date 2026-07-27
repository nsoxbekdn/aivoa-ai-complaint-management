"""Tests for POST /api/complaints/analyze. The Groq client is always mocked."""

import io

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

SAMPLE_TEXT = (
    "From: quality@meridianpharmacy.example\n"
    "Subject: Cracked capsules - Amoxinova 500 mg Capsules, batch AMX-24118\n\n"
    "On 14 June 2026 our pharmacist opened a blister strip of Amoxinova 500 mg Capsules "
    "(batch AMX-24118, mfg 2025-11-02, exp 2027-10-31) and found 12 cracked capsules with "
    "powder leakage. Please advise. - Meridian Pharmacy Group"
)


def test_analyze_requires_some_input(client: TestClient) -> None:
    response = client.post("/api/complaints/analyze", data={"complaint_text": "   "})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_analyze_rejects_non_pdf_upload(client: TestClient) -> None:
    files = {"file": ("notes.txt", io.BytesIO(b"plain text"), "text/plain")}

    response = client.post("/api/complaints/analyze", files=files)

    assert response.status_code == 415
    assert "PDF" in response.json()["error"]["message"]


def test_analyze_rejects_unreadable_pdf(client: TestClient) -> None:
    files = {"file": ("broken.pdf", io.BytesIO(b"not really a pdf"), "application/pdf")}

    response = client.post("/api/complaints/analyze", files=files)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_analyze_returns_503_when_llm_not_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "groq_api_key", "", raising=False)

    response = client.post("/api/complaints/analyze", data={"complaint_text": SAMPLE_TEXT})

    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["error"]["message"]


def test_analyze_populates_every_section(client: TestClient, mock_llm: None) -> None:
    response = client.post("/api/complaints/analyze", data={"complaint_text": SAMPLE_TEXT})

    assert response.status_code == 200
    body = response.json()

    assert body["extracted_fields"]["batch_lot_number"] == "AMX-24118"
    assert body["extracted_fields"]["complaint_date"] == "2026-06-14"
    assert body["extracted_fields"]["quantity_affected"] == 12
    assert body["completeness"]["score"] > 0
    assert body["risk_assessment"]["risk_level"] in {"low", "medium", "high", "critical"}
    assert body["summary"]
    assert body["recommendations"]["possible_root_causes"]
    assert "review" in body["disclaimer"].lower()


def test_analyze_accepts_json_body(client: TestClient, mock_llm: None) -> None:
    response = client.post("/api/complaints/analyze", json={"complaint_text": SAMPLE_TEXT})

    assert response.status_code == 200
    assert response.json()["extracted_fields"]["product_name"] == "Amoxinova 500 mg Capsules"


def test_analyze_discards_ungrounded_batch_number(
    client: TestClient, mock_llm: None
) -> None:
    """The fake model returns batch AMX-24118; this text never mentions it, so it must be dropped."""
    text = "The tablets in the bottle we received last week are discoloured. Please investigate."

    response = client.post("/api/complaints/analyze", data={"complaint_text": text})

    body = response.json()
    assert body["extracted_fields"]["batch_lot_number"] is None
    assert any("does not appear in the source document" in w for w in body["warnings"])


def test_analyze_does_not_save_anything(client: TestClient, mock_llm: None) -> None:
    client.post("/api/complaints/analyze", data={"complaint_text": SAMPLE_TEXT})

    assert client.get("/api/complaints").json()["total"] == 0
