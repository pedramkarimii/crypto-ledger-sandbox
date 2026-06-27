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


def test_wallet_balances_reflect_funding() -> None:
    asyncio.run(prepare_database())

    email = f"balance-{uuid4().hex}@example.com"
    password = "CryptoLedger123!"
    amount = Decimal("3.500000")

    with TestClient(app) as client:
        register_response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert register_response.status_code == 201

        access_token = register_response.json()["access_token"]
        authorization = {"Authorization": f"Bearer {access_token}"}

        fund_response = client.post(
            "/api/v1/wallets/fund",
            headers={
                **authorization,
                "Idempotency-Key": f"balance-funding-{uuid4().hex}",
            },
            json={"asset_code": "USDT", "amount": str(amount)},
        )
        assert fund_response.status_code == 201

        balances_response = client.get(
            "/api/v1/wallets",
            headers=authorization,
        )

    assert balances_response.status_code == 200
    balances = balances_response.json()["balances"]
    assert len(balances) == 1

    balance = balances[0]
    assert balance["asset_code"] == "USDT"
    assert Decimal(balance["available_balance"]) == amount
    assert Decimal(balance["locked_balance"]) == Decimal("0")
    assert Decimal(balance["total_balance"]) == amount
