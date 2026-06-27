from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_service_metadata() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "development",
        "service": "Crypto Ledger Sandbox",
    }
