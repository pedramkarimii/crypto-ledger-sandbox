import asyncio
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionFactory, engine
from app.models.enums import (
    BalanceBucket,
    LedgerEntryType,
    LedgerTransactionType,
    OrderSide,
    OrderStatus,
)
from app.models.ledger import LedgerEntry, LedgerTransaction
from app.models.user import User
from app.models.wallet import Wallet
from app.scripts.seed_dev_data import main as seed_development_data
from app.services.ledger import post_sandbox_funding
from app.services.orders import (
    cancel_order_reservation,
    create_order_reservation,
)


def test_cancel_order_releases_balance_and_replays_safely() -> None:
    asyncio.run(exercise_cancel_order())


async def exercise_cancel_order() -> None:
    try:
        await seed_development_data()

        async with AsyncSessionFactory() as session:
            user = User(
                email=f"cancel-{uuid4().hex}@example.com",
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
                idempotency_key=f"cancel-funding-{uuid4().hex}",
            )
            reservation = await create_order_reservation(
                session,
                user_id=user.id,
                base_asset_code="BTC",
                quote_asset_code="USDT",
                side=OrderSide.BUY,
                price=Decimal("20000"),
                quantity=Decimal("0.001"),
                idempotency_key=f"cancel-order-{uuid4().hex}",
            )

            first_cancel = await cancel_order_reservation(
                session,
                user_id=user.id,
                order_id=reservation.order.id,
            )
            replay_cancel = await cancel_order_reservation(
                session,
                user_id=user.id,
                order_id=reservation.order.id,
            )

            assert first_cancel.replayed is False
            assert replay_cancel.replayed is True
            assert first_cancel.order.status == OrderStatus.CANCELED

            wallet = await session.scalar(
                select(Wallet).where(
                    Wallet.user_id == user.id,
                    Wallet.asset_id == reservation.reserve_asset.id,
                )
            )
            assert wallet is not None
            assert wallet.available_balance == Decimal("100")
            assert wallet.locked_balance == Decimal("0")

            release = await session.scalar(
                select(LedgerTransaction).where(
                    LedgerTransaction.transaction_type
                    == LedgerTransactionType.ORDER_RELEASE,
                    LedgerTransaction.description.contains(str(reservation.order.id)),
                )
            )
            assert release is not None

            entries = (
                await session.scalars(
                    select(LedgerEntry)
                    .where(LedgerEntry.transaction_id == release.id)
                    .order_by(LedgerEntry.sequence)
                )
            ).all()
            assert [(entry.entry_type, entry.balance_bucket) for entry in entries] == [
                (LedgerEntryType.DEBIT, BalanceBucket.LOCKED),
                (LedgerEntryType.CREDIT, BalanceBucket.AVAILABLE),
            ]
            assert [entry.amount for entry in entries] == [
                Decimal("20"),
                Decimal("20"),
            ]
    finally:
        await engine.dispose()
