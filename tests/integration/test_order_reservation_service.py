import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionFactory, engine
from app.models.enums import BalanceBucket, LedgerEntryType, OrderSide
from app.models.ledger import LedgerEntry
from app.models.user import User
from app.models.wallet import Wallet
from app.scripts.seed_dev_data import main as seed_development_data
from app.services.ledger import post_sandbox_funding
from app.services.orders import (
    InsufficientAvailableBalanceError,
    OrderIdempotencyConflictError,
    create_order_reservation,
)


def test_order_reservations_move_balances_and_replay_safely() -> None:
    asyncio.run(exercise_order_reservations())


async def exercise_order_reservations() -> None:
    try:
        await seed_development_data()

        async with AsyncSessionFactory() as session:
            user = User(
                email=f"orders-{uuid4().hex}@example.com",
                hashed_password=hash_password("CryptoLedger123!"),
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            await post_sandbox_funding(
                session,
                user_id=user.id,
                asset_code="USDT",
                amount=Decimal("100"),
                idempotency_key=f"fund-usdt-{uuid4().hex}",
            )
            await post_sandbox_funding(
                session,
                user_id=user.id,
                asset_code="BTC",
                amount=Decimal("0.01000000"),
                idempotency_key=f"fund-btc-{uuid4().hex}",
            )

            buy_key = f"buy-order-{uuid4().hex}"
            buy_result = await create_order_reservation(
                session,
                user_id=user.id,
                base_asset_code="BTC",
                quote_asset_code="USDT",
                side=OrderSide.BUY,
                price=Decimal("20000"),
                quantity=Decimal("0.001"),
                idempotency_key=buy_key,
            )
            assert buy_result.replayed is False
            assert buy_result.reserve_asset.code == "USDT"
            assert buy_result.order.reserved_amount == Decimal("20")

            buy_replay = await create_order_reservation(
                session,
                user_id=user.id,
                base_asset_code="BTC",
                quote_asset_code="USDT",
                side=OrderSide.BUY,
                price=Decimal("20000"),
                quantity=Decimal("0.001"),
                idempotency_key=buy_key,
            )
            assert buy_replay.replayed is True
            assert buy_replay.order.id == buy_result.order.id

            usdt_wallet = await session.scalar(
                select(Wallet).where(
                    Wallet.user_id == user.id,
                    Wallet.asset_id == buy_result.reserve_asset.id,
                )
            )
            assert usdt_wallet is not None
            assert usdt_wallet.available_balance == Decimal("80")
            assert usdt_wallet.locked_balance == Decimal("20")

            buy_entries = (
                await session.scalars(
                    select(LedgerEntry)
                    .where(
                        LedgerEntry.transaction_id
                        == buy_result.order.reservation_transaction_id
                    )
                    .order_by(LedgerEntry.sequence)
                )
            ).all()
            assert [
                (entry.entry_type, entry.balance_bucket) for entry in buy_entries
            ] == [
                (LedgerEntryType.DEBIT, BalanceBucket.AVAILABLE),
                (LedgerEntryType.CREDIT, BalanceBucket.LOCKED),
            ]
            assert [entry.amount for entry in buy_entries] == [
                Decimal("20"),
                Decimal("20"),
            ]

            sell_result = await create_order_reservation(
                session,
                user_id=user.id,
                base_asset_code="BTC",
                quote_asset_code="USDT",
                side=OrderSide.SELL,
                price=Decimal("25000"),
                quantity=Decimal("0.004"),
                idempotency_key=f"sell-order-{uuid4().hex}",
            )
            assert sell_result.replayed is False
            assert sell_result.reserve_asset.code == "BTC"
            assert sell_result.order.reserved_amount == Decimal("0.004")

            btc_wallet = await session.scalar(
                select(Wallet).where(
                    Wallet.user_id == user.id,
                    Wallet.asset_id == sell_result.reserve_asset.id,
                )
            )
            assert btc_wallet is not None
            assert btc_wallet.available_balance == Decimal("0.006")
            assert btc_wallet.locked_balance == Decimal("0.004")

            with pytest.raises(OrderIdempotencyConflictError):
                await create_order_reservation(
                    session,
                    user_id=user.id,
                    base_asset_code="BTC",
                    quote_asset_code="USDT",
                    side=OrderSide.BUY,
                    price=Decimal("21000"),
                    quantity=Decimal("0.001"),
                    idempotency_key=buy_key,
                )

            with pytest.raises(InsufficientAvailableBalanceError):
                await create_order_reservation(
                    session,
                    user_id=user.id,
                    base_asset_code="BTC",
                    quote_asset_code="USDT",
                    side=OrderSide.BUY,
                    price=Decimal("100000"),
                    quantity=Decimal("1"),
                    idempotency_key=f"insufficient-{uuid4().hex}",
                )
    finally:
        await engine.dispose()
