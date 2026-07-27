"""The final handoff must analyse and persist the form the reporter actually reviewed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.llm.groq_client import LLMError


def _payload() -> dict:
    return {
        "fields": {
            "complaint_source": "customer_email",
            "customer_name": "Meridian Pharmacy Group",
            "customer_contact": "quality@meridian.example",
            "product_name": "ClearCough Syrup 100 ml",
            "product_strength_grade": "5 mg/5 ml",
            "batch_lot_number": "CC26045",
            "manufacturing_date": "2025-04-10",
            "expiry_date": "2027-04-09",
            "quantity_affected": 5,
            "quantity_unit": "bottles",
            "complaint_type": "packaging_defect",
            "complaint_date": "2026-07-25",
            "complaint_details": "Five bottles were leaking because the caps appeared loose.",
        },
        "original_text": "The original email did not include the manufacturing or expiry date.",
        "input_filename": "scanned-complaint.png",
        "intake_transcript": [
            {"role": "assistant", "text": "What are the printed product dates?"},
            {"role": "user", "text": "Manufactured 2025-04-10, expiry 2027-04-09."},
        ],
        "source_documents": [
            {
                "filename": "scanned-complaint.png",
                "media_type": "image/png",
                "extraction_method": "groq_vision",
                "text": "Five ClearCough bottles leaked. Batch CC26045.",
                "page_count": 1,
                "ocr_used": True,
            }
        ],
        "warnings": ["Groq Vision OCR was used — please verify the extracted details."],
    }


def test_finalize_uses_edited_dates_for_analysis_and_persistence(
    client: TestClient,
    mock_llm: None,
) -> None:
    response = client.post("/api/complaints/finalize", json=_payload())

    assert response.status_code == 201
    complaint = response.json()
    assert complaint["manufacturing_date"] == "2025-04-10"
    assert complaint["expiry_date"] == "2027-04-09"
    assert "2025-04-10" in complaint["ai_summary"]
    assert "2027-04-09" in complaint["ai_summary"]
    assert "manufacturing date" not in complaint["missing_fields"]
    assert "expiry date" not in complaint["missing_fields"]
    assert "initial severity" not in complaint["missing_fields"]
    assert "priority" not in complaint["missing_fields"]
    assert complaint["source_documents"][0]["ocr_used"] is True
    assert "verify" in complaint["analysis_warnings"][0].lower()

    fetched = client.get(f"/api/complaints/{complaint['id']}").json()
    assert fetched["manufacturing_date"] == "2025-04-10"
    assert fetched["source_documents"][0]["filename"] == "scanned-complaint.png"


def test_provider_failure_still_lodges_with_factual_summary_and_warning(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args, **_kwargs) -> dict:
        raise LLMError("provider unavailable")

    for module in (
        "app.graph.nodes.completeness_node",
        "app.graph.nodes.risk",
        "app.graph.nodes.summary",
        "app.graph.nodes.recommendations",
    ):
        monkeypatch.setattr(f"{module}.complete_json", unavailable)

    response = client.post("/api/complaints/finalize", json=_payload())

    assert response.status_code == 201
    complaint = response.json()
    assert "2025-04-10" in complaint["ai_summary"]
    assert "2027-04-09" in complaint["ai_summary"]
    assert any("unavailable" in warning.lower() or "failed" in warning.lower() for warning in complaint["analysis_warnings"])
    assert complaint["root_cause_recommendations"]
