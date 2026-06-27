import asyncio
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.db.session import AsyncSessionFactory, engine
from app.models.enums import BalanceBucket, LedgerEntryType, WalletOwnerType
from app.models.ledger import LedgerEntry
from app.models.user import User
from app.models.wallet import Wallet
from app.scripts.seed_dev_data import main as seed_development_data
from app.services.ledger import (
    TREASURY_ACCOUNT,
    IdempotencyConflictError,
    post_sandbox_funding,
)


def test_sandbox_funding_is_balanced_and_idempotent() -> None:
    asyncio.run(exercise_sandbox_funding())


async def exercise_sandbox_funding() -> None:
    try:
        await _exercise_sandbox_funding()
    finally:
        await engine.dispose()


async def _exercise_sandbox_funding() -> None:
    await seed_development_data()

    email = f"ledger-{uuid4().hex}@example.com"
    amount = Decimal("12.500000")
    idempotency_key = f"funding-{uuid4().hex}"

    async with AsyncSessionFactory() as session:
        user = User(
            email=email,
            hashed_password="test-only-not-a-real-password-hash",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        treasury_wallet = await session.scalar(
            select(Wallet).where(
                Wallet.owner_type == WalletOwnerType.SYSTEM,
                Wallet.system_account == TREASURY_ACCOUNT,
            )
        )
        assert treasury_wallet is not None
        treasury_balance_before = treasury_wallet.available_balance

        first_result = await post_sandbox_funding(
            session,
            user_id=user.id,
            asset_code="USDT",
            amount=amount,
            idempotency_key=idempotency_key,
        )
        replay_result = await post_sandbox_funding(
            session,
            user_id=user.id,
            asset_code="USDT",
            amount=amount,
            idempotency_key=idempotency_key,
        )

        assert first_result.replayed is False
        assert replay_result.replayed is True
        assert first_result.transaction.id == replay_result.transaction.id

        user_wallet = await session.scalar(
            select(Wallet).where(
                Wallet.owner_type == WalletOwnerType.USER,
                Wallet.user_id == user.id,
            )
        )
        assert user_wallet is not None
        assert user_wallet.available_balance == amount
        assert user_wallet.locked_balance == Decimal("0")

        await session.refresh(treasury_wallet)
        assert treasury_wallet.available_balance == treasury_balance_before - amount

        entries = (
            await session.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.transaction_id == first_result.transaction.id)
                .order_by(LedgerEntry.sequence)
            )
        ).all()

        assert len(entries) == 2
        assert entries[0].entry_type == LedgerEntryType.DEBIT
        assert entries[1].entry_type == LedgerEntryType.CREDIT
        assert entries[0].balance_bucket == BalanceBucket.AVAILABLE
        assert entries[1].balance_bucket == BalanceBucket.AVAILABLE
        assert entries[0].amount == amount
        assert entries[1].amount == amount

        try:
            await post_sandbox_funding(
                session,
                user_id=user.id,
                asset_code="USDT",
                amount=Decimal("13.000000"),
                idempotency_key=idempotency_key,
            )
        except IdempotencyConflictError:
            pass
        else:
            raise AssertionError("Expected an idempotency conflict.")
