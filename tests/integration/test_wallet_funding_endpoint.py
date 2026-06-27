import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import engine
from app.main import app
from app.scripts.seed_dev_data import main as seed_development_data


async def prepare_database() -> None:
    await seed_development_data()
    await engine.dispose()


def test_wallet_funding_endpoint_is_idempotent() -> None:
    asyncio.run(prepare_database())

    email = f"wallet-{uuid4().hex}@example.com"
    password = "CryptoLedger123!"
    idempotency_key = f"wallet-funding-{uuid4().hex}"
    payload = {"asset_code": "USDT", "amount": "7.250000"}

    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert register_response.status_code == 201

        access_token = register_response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": idempotency_key,
        }

        first_response = client.post(
            "/api/v1/wallets/fund",
            headers=headers,
            json=payload,
        )
        replay_response = client.post(
            "/api/v1/wallets/fund",
            headers=headers,
            json=payload,
        )
        conflict_response = client.post(
            "/api/v1/wallets/fund",
            headers=headers,
            json={"asset_code": "USDT", "amount": "8.000000"},
        )
        unauthenticated_response = client.post(
            "/api/v1/wallets/fund",
            headers={"Idempotency-Key": f"missing-auth-{uuid4().hex}"},
            json=payload,
        )

    assert first_response.status_code == 201
    assert first_response.json()["replayed"] is False
    assert replay_response.status_code == 200
    assert replay_response.json()["replayed"] is True
    assert (
        first_response.json()["transaction_id"]
        == replay_response.json()["transaction_id"]
    )
    assert conflict_response.status_code == 409
    assert unauthenticated_response.status_code == 401
