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


def test_cancel_order_endpoint_releases_balance_and_replays_safely() -> None:
    asyncio.run(prepare_database())

    email = f"order-cancel-api-{uuid4().hex}@example.com"
    password = "CryptoLedger123!"
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

        funding_response = client.post(
            "/api/v1/wallets/fund",
            headers={
                **authorization,
                "Idempotency-Key": f"cancel-api-funding-{uuid4().hex}",
            },
            json={"asset_code": "USDT", "amount": "100"},
        )
        assert funding_response.status_code == 201

        create_response = client.post(
            "/api/v1/orders",
            headers={
                **authorization,
                "Idempotency-Key": f"cancel-api-order-{uuid4().hex}",
            },
            json=order_payload,
        )
        assert create_response.status_code == 201
        created_order = create_response.json()
        assert created_order["status"] == "open"
        assert Decimal(created_order["reserved_amount"]) == Decimal("20")

        cancel_response = client.post(
            f"/api/v1/orders/{created_order['id']}/cancel",
            headers=authorization,
        )
        assert cancel_response.status_code == 200
        canceled_order = cancel_response.json()
        assert canceled_order["id"] == created_order["id"]
        assert canceled_order["status"] == "canceled"
        assert canceled_order["replayed"] is False
        assert canceled_order["reserved_asset_code"] == "USDT"

        replay_response = client.post(
            f"/api/v1/orders/{created_order['id']}/cancel",
            headers=authorization,
        )
        assert replay_response.status_code == 200
        replayed_order = replay_response.json()
        assert replayed_order["id"] == created_order["id"]
        assert replayed_order["status"] == "canceled"
        assert replayed_order["replayed"] is True

        balances_response = client.get(
            "/api/v1/wallets",
            headers=authorization,
        )
        assert balances_response.status_code == 200
        balances = {
            balance["asset_code"]: balance
            for balance in balances_response.json()["balances"]
        }
        assert Decimal(balances["USDT"]["available_balance"]) == Decimal("100")
        assert Decimal(balances["USDT"]["locked_balance"]) == Decimal("0")
