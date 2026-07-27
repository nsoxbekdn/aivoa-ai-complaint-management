"""Test fixtures.

Environment variables are set before `app` is imported, because app.config caches settings
on first use. Tests run against a throwaway SQLite file and never touch the network.
"""

import os
import tempfile
from collections.abc import Iterator

import pytest

_DB_FILE = os.path.join(tempfile.gettempdir(), "aivoa_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ["GROQ_API_KEY"] = "test-key-not-real"
os.environ["FRONTEND_ORIGIN"] = "http://localhost:5173"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database() -> Iterator[None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def valid_complaint_payload() -> dict:
    return {
        "complaint_source": "customer_email",
        "customer_name": "Meridian Pharmacy Group",
        "customer_contact": "quality@meridianpharmacy.example",
        "product_name": "Amoxinova 500 mg Capsules",
        "product_strength_grade": "500 mg",
        "batch_lot_number": "AMX-24118",
        "complaint_type": "product_quality_defect",
        "complaint_date": "2026-06-14",
        "complaint_details": "Twelve capsules in the blister were cracked and powder had leaked out.",
        "initial_severity": "major",
        "priority": "high",
    }


# --- fake LLM ------------------------------------------------------------------------

FAKE_EXTRACTION = {
    "complaint_source": "customer_email",
    "customer_name": "Meridian Pharmacy Group",
    "customer_contact": "quality@meridianpharmacy.example",
    "product_name": "Amoxinova 500 mg Capsules",
    "product_strength_grade": "500 mg",
    "batch_lot_number": "AMX-24118",
    "manufacturing_date": "2025-11-02",
    "expiry_date": "2027-10-31",
    "quantity_affected": 12,
    "quantity_unit": "capsules",
    "complaint_type": "product_quality_defect",
    "complaint_date": "2026-06-14",
    "complaint_details": "Cracked capsules with powder leakage were found in one blister strip.",
    "initial_severity": "major",
    "priority": "high",
}


def fake_complete_json(
    system_prompt: str, user_prompt: str, *, max_tokens: int = 1200, schema: object = None
) -> dict:
    """Route on the system prompt so one fake covers every node."""
    if "intake assistant" in system_prompt:
        return dict(FAKE_EXTRACTION)
    if "follow-up questions" in system_prompt:
        return {"follow_up_questions": ["Is a retained sample available for inspection?"]}
    if "risk assessor" in system_prompt:
        return {
            "risk_level": "medium",
            "severity": "major",
            "priority": "high",
            "patient_safety_concern": False,
            "product_quality_concern": True,
            "rationale": "Physical defect affecting a limited number of capsules.",
            "confidence": 0.7,
        }
    if "summarise" in system_prompt:
        return {"summary": "Cracked Amoxinova capsules reported by a pharmacy group."}
    if "investigator" in system_prompt:
        return {
            "possible_root_causes": ["Excessive compression force during encapsulation"],
            "initial_investigation_steps": ["Review batch record for AMX-24118"],
            "preliminary_capa_suggestions": ["Re-qualify the encapsulation line"],
        }
    return {}


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the LLM call in every node module. No network call can happen in tests."""
    for module in (
        "app.graph.nodes.extract",
        "app.graph.nodes.completeness_node",
        "app.graph.nodes.risk",
        "app.graph.nodes.summary",
        "app.graph.nodes.recommendations",
    ):
        monkeypatch.setattr(f"{module}.complete_json", fake_complete_json)
