from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_register_login_and_read_current_user() -> None:
    email = f"auth-{uuid4().hex}@example.com"
    password = "CryptoLedger123!"

    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert register_response.status_code == 201

        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_response.status_code == 200

        token = login_response.json()["access_token"]
        me_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == email
    assert me_response.json()["is_active"] is True


def test_me_rejects_missing_token() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
