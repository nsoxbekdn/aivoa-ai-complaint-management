from fastapi.testclient import TestClient

from app.services.duplicates import _COMPARE_CHARS, _normalise
from tests.test_analyze import SAMPLE_TEXT


def test_comparison_text_is_capped() -> None:
    """SequenceMatcher is O(n*m): a 1 MB complaint against 50 stored rows measured at 91
    seconds of blocking CPU before this cap existed."""
    assert len(_normalise("a" * 1_000_000)) == _COMPARE_CHARS


def test_analyze_flags_an_existing_complaint_for_the_same_batch(
    client: TestClient, mock_llm: None, valid_complaint_payload: dict
) -> None:
    client.post("/api/complaints", json=valid_complaint_payload)

    body = client.post("/api/complaints/analyze", data={"complaint_text": SAMPLE_TEXT}).json()

    candidates = body["duplicate_candidates"]
    assert candidates, "an identical batch + product should surface as a possible duplicate"
    assert candidates[0]["batch_lot_number"] == "AMX-24118"
    assert "same batch number" in candidates[0]["reason"]
    assert 0 < candidates[0]["similarity"] <= 1


def test_unrelated_complaint_is_not_flagged(client: TestClient, mock_llm: None) -> None:
    body = client.post("/api/complaints/analyze", data={"complaint_text": SAMPLE_TEXT}).json()

    assert body["duplicate_candidates"] == []
