from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_process_liveness():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "scope": "process"}


def test_openapi_available():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
