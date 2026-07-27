from fastapi.testclient import TestClient


def test_health_reports_database_and_model(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["llm_configured"] is True
    assert body["llm_model"]  # model name comes from the environment, never hardcoded
