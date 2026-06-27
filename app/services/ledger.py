from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.enums import (
    BalanceBucket,
    LedgerEntryType,
    LedgerTransactionStatus,
    LedgerTransactionType,
    WalletOwnerType,
)
from app.models.ledger import LedgerEntry, LedgerTransaction
from app.models.wallet import Wallet

TREASURY_ACCOUNT = "funding_treasury"


class LedgerServiceError(Exception):
    pass


class AssetNotFoundError(LedgerServiceError):
    pass


class TreasuryNotInitializedError(LedgerServiceError):
    pass


class InsufficientTreasuryBalanceError(LedgerServiceError):
    pass


class IdempotencyConflictError(LedgerServiceError):
    pass


@dataclass(frozen=True)
class FundingResult:
    transaction: LedgerTransaction
    asset: Asset
    replayed: bool


async def find_funding_replay(
    session: AsyncSession,
    *,
    idempotency_key: str,
    user_id: UUID,
    asset: Asset,
    amount: Decimal,
) -> FundingResult | None:
    transaction = await session.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.idempotency_key == idempotency_key
        )
    )
    if transaction is None:
        return None

    if (
        transaction.transaction_type != LedgerTransactionType.FUNDING
        or transaction.status != LedgerTransactionStatus.POSTED
    ):
        raise IdempotencyConflictError

    matching_entry = await session.scalar(
        select(LedgerEntry)
        .join(Wallet, LedgerEntry.wallet_id == Wallet.id)
        .where(
            LedgerEntry.transaction_id == transaction.id,
            LedgerEntry.entry_type == LedgerEntryType.CREDIT,
            LedgerEntry.balance_bucket == BalanceBucket.AVAILABLE,
            LedgerEntry.amount == amount,
            Wallet.user_id == user_id,
            Wallet.asset_id == asset.id,
        )
    )
    if matching_entry is None:
        raise IdempotencyConflictError

    return FundingResult(transaction=transaction, asset=asset, replayed=True)


async def post_sandbox_funding(
    session: AsyncSession,
    *,
    user_id: UUID,
    asset_code: str,
    amount: Decimal,
    idempotency_key: str,
) -> FundingResult:
    if amount <= 0:
        raise ValueError("Funding amount must be greater than zero.")

    asset = await session.scalar(
        select(Asset).where(
            Asset.code == asset_code.upper(),
            Asset.is_active.is_(True),
        )
    )
    if asset is None:
        raise AssetNotFoundError

    replay = await find_funding_replay(
        session,
        idempotency_key=idempotency_key,
        user_id=user_id,
        asset=asset,
        amount=amount,
    )
    if replay is not None:
        return replay

    treasury_wallet = await session.scalar(
        select(Wallet)
        .where(
            Wallet.owner_type == WalletOwnerType.SYSTEM,
            Wallet.system_account == TREASURY_ACCOUNT,
            Wallet.asset_id == asset.id,
        )
        .with_for_update()
    )
    if treasury_wallet is None:
        raise TreasuryNotInitializedError

    if treasury_wallet.available_balance < amount:
        raise InsufficientTreasuryBalanceError

    user_wallet = await session.scalar(
        select(Wallet)
        .where(
            Wallet.owner_type == WalletOwnerType.USER,
            Wallet.user_id == user_id,
            Wallet.asset_id == asset.id,
        )
        .with_for_update()
    )
    if user_wallet is None:
        user_wallet = Wallet(
            user_id=user_id,
            asset_id=asset.id,
            owner_type=WalletOwnerType.USER,
            available_balance=Decimal("0"),
            locked_balance=Decimal("0"),
        )
        session.add(user_wallet)
        await session.flush()

    transaction = LedgerTransaction(
        reference=f"FND-{uuid4().hex[:20].upper()}",
        idempotency_key=idempotency_key,
        transaction_type=LedgerTransactionType.FUNDING,
        status=LedgerTransactionStatus.POSTED,
        description=f"Sandbox funding for {asset.code}",
    )
    session.add(transaction)
    await session.flush()

    treasury_wallet.available_balance -= amount
    user_wallet.available_balance += amount

    session.add_all(
        [
            LedgerEntry(
                transaction_id=transaction.id,
                wallet_id=treasury_wallet.id,
                entry_type=LedgerEntryType.DEBIT,
                balance_bucket=BalanceBucket.AVAILABLE,
                amount=amount,
                sequence=1,
                description="Debit sandbox treasury",
            ),
            LedgerEntry(
                transaction_id=transaction.id,
                wallet_id=user_wallet.id,
                entry_type=LedgerEntryType.CREDIT,
                balance_bucket=BalanceBucket.AVAILABLE,
                amount=amount,
                sequence=2,
                description="Credit user wallet",
            ),
        ]
    )

    await session.commit()
    await session.refresh(transaction)

    return FundingResult(transaction=transaction, asset=asset, replayed=False)
