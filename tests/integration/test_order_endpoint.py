import asyncio
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import engine
from app.main import app
from app.scripts.seed_dev_data import main as seed_development_data


async def prepare_database() -> None:
    await seed_development_data()
    await engine.dispose()


def test_create_order_reserves_balance_and_replays_safely() -> None:
    asyncio.run(prepare_database())

    email = f"order-api-{uuid4().hex}@example.com"
    password = "CryptoLedger123!"
    order_key = f"order-buy-{uuid4().hex}"
    order_payload = {
        "base_asset_code": "BTC",
        "quote_asset_code": "USDT",
        "side": "buy",
        "price": "20000",
        "quantity": "0.001",
    }

    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert register_response.status_code == 201

        access_token = register_response.json()["access_token"]
        authorization = {"Authorization": f"Bearer {access_token}"}

        for asset_code, amount in (("USDT", "100"), ("BTC", "0.01000000")):
            funding_response = client.post(
                "/api/v1/wallets/fund",
                headers={
                    **authorization,
                    "Idempotency-Key": f"order-funding-{asset_code}-{uuid4().hex}",
                },
                json={"asset_code": asset_code, "amount": amount},
            )
            assert funding_response.status_code == 201

        create_response = client.post(
            "/api/v1/orders",
            headers={
                **authorization,
                "Idempotency-Key": order_key,
            },
            json=order_payload,
        )
        assert create_response.status_code == 201
        created_order = create_response.json()
        assert created_order["replayed"] is False
        assert created_order["base_asset_code"] == "BTC"
        assert created_order["quote_asset_code"] == "USDT"
        assert created_order["side"] == "buy"
        assert created_order["status"] == "open"
        assert Decimal(created_order["reserved_amount"]) == Decimal("20")
        assert created_order["reserved_asset_code"] == "USDT"

        replay_response = client.post(
            "/api/v1/orders",
            headers={
                **authorization,
                "Idempotency-Key": order_key,
            },
            json=order_payload,
        )
        assert replay_response.status_code == 200
        replayed_order = replay_response.json()
        assert replayed_order["replayed"] is True
        assert replayed_order["id"] == created_order["id"]

        conflict_response = client.post(
            "/api/v1/orders",
            headers={
                **authorization,
                "Idempotency-Key": order_key,
            },
            json={**order_payload, "price": "21000"},
        )
        assert conflict_response.status_code == 409

        balances_response = client.get(
            "/api/v1/wallets",
            headers=authorization,
        )
        assert balances_response.status_code == 200

    balances = {
        balance["asset_code"]: balance
        for balance in balances_response.json()["balances"]
    }
    assert Decimal(balances["USDT"]["available_balance"]) == Decimal("80")
    assert Decimal(balances["USDT"]["locked_balance"]) == Decimal("20")
    assert Decimal(balances["BTC"]["available_balance"]) == Decimal("0.01000000")
    assert Decimal(balances["BTC"]["locked_balance"]) == Decimal("0")
