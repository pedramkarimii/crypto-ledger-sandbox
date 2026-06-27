from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.enums import (
    BalanceBucket,
    LedgerEntryType,
    LedgerTransactionStatus,
    LedgerTransactionType,
    OrderSide,
    OrderStatus,
    WalletOwnerType,
)
from app.models.ledger import LedgerEntry, LedgerTransaction
from app.models.order import Order
from app.models.wallet import Wallet


class OrderServiceError(Exception):
    pass


class OrderAssetNotFoundError(OrderServiceError):
    pass


class InsufficientAvailableBalanceError(OrderServiceError):
    pass


class OrderIdempotencyConflictError(OrderServiceError):
    pass


@dataclass(frozen=True)
class OrderReservationResult:
    order: Order
    base_asset: Asset
    quote_asset: Asset
    reserve_asset: Asset
    replayed: bool


def reservation_amount(
    *,
    side: OrderSide,
    price: Decimal,
    quantity: Decimal,
) -> Decimal:
    if price <= 0 or quantity <= 0:
        raise ValueError("Order price and quantity must be greater than zero.")

    if side == OrderSide.BUY:
        return price * quantity
    return quantity


def ledger_idempotency_key(*, user_id: UUID, idempotency_key: str) -> str:
    value = f"{user_id}:{idempotency_key}".encode()
    return sha256(value).hexdigest()


async def active_asset(session: AsyncSession, asset_code: str) -> Asset:
    asset = await session.scalar(
        select(Asset).where(
            Asset.code == asset_code.upper(),
            Asset.is_active.is_(True),
        )
    )
    if asset is None:
        raise OrderAssetNotFoundError(f"Unknown active asset: {asset_code}.")
    return asset


def validate_replay(
    *,
    order: Order,
    base_asset: Asset,
    quote_asset: Asset,
    side: OrderSide,
    price: Decimal,
    quantity: Decimal,
) -> None:
    if (
        order.base_asset_id != base_asset.id
        or order.quote_asset_id != quote_asset.id
        or order.side != side
        or order.price != price
        or order.quantity != quantity
    ):
        raise OrderIdempotencyConflictError(
            "Idempotency key was already used with different order data."
        )


async def existing_order_replay(
    session: AsyncSession,
    *,
    user_id: UUID,
    idempotency_key: str,
    base_asset: Asset,
    quote_asset: Asset,
    side: OrderSide,
    price: Decimal,
    quantity: Decimal,
) -> Order | None:
    order = await session.scalar(
        select(Order).where(
            Order.user_id == user_id,
            Order.idempotency_key == idempotency_key,
        )
    )
    if order is None:
        return None

    validate_replay(
        order=order,
        base_asset=base_asset,
        quote_asset=quote_asset,
        side=side,
        price=price,
        quantity=quantity,
    )
    return order


async def create_order_reservation(
    session: AsyncSession,
    *,
    user_id: UUID,
    base_asset_code: str,
    quote_asset_code: str,
    side: OrderSide,
    price: Decimal,
    quantity: Decimal,
    idempotency_key: str,
) -> OrderReservationResult:
    base_asset = await active_asset(session, base_asset_code)
    quote_asset = await active_asset(session, quote_asset_code)
    if base_asset.id == quote_asset.id:
        raise ValueError("Base and quote assets must be different.")

    reserved_amount = reservation_amount(
        side=side,
        price=price,
        quantity=quantity,
    )
    reserve_asset = quote_asset if side == OrderSide.BUY else base_asset

    replay = await existing_order_replay(
        session,
        user_id=user_id,
        idempotency_key=idempotency_key,
        base_asset=base_asset,
        quote_asset=quote_asset,
        side=side,
        price=price,
        quantity=quantity,
    )
    if replay is not None:
        return OrderReservationResult(
            order=replay,
            base_asset=base_asset,
            quote_asset=quote_asset,
            reserve_asset=reserve_asset,
            replayed=True,
        )

    wallet = await session.scalar(
        select(Wallet)
        .where(
            Wallet.owner_type == WalletOwnerType.USER,
            Wallet.user_id == user_id,
            Wallet.asset_id == reserve_asset.id,
        )
        .with_for_update()
    )
    if wallet is None or wallet.available_balance < reserved_amount:
        raise InsufficientAvailableBalanceError(
            f"Insufficient available {reserve_asset.code} balance."
        )

    replay = await existing_order_replay(
        session,
        user_id=user_id,
        idempotency_key=idempotency_key,
        base_asset=base_asset,
        quote_asset=quote_asset,
        side=side,
        price=price,
        quantity=quantity,
    )
    if replay is not None:
        return OrderReservationResult(
            order=replay,
            base_asset=base_asset,
            quote_asset=quote_asset,
            reserve_asset=reserve_asset,
            replayed=True,
        )

    transaction = LedgerTransaction(
        reference=f"ORD-{uuid4().hex[:20].upper()}",
        idempotency_key=ledger_idempotency_key(
            user_id=user_id,
            idempotency_key=idempotency_key,
        ),
        transaction_type=LedgerTransactionType.ORDER_RESERVE,
        status=LedgerTransactionStatus.POSTED,
        description=(
            f"Reserve {reserved_amount} {reserve_asset.code} for {side.value} order"
        ),
    )
    session.add(transaction)
    await session.flush()

    order = Order(
        user_id=user_id,
        base_asset_id=base_asset.id,
        quote_asset_id=quote_asset.id,
        idempotency_key=idempotency_key,
        reservation_transaction_id=transaction.id,
        side=side,
        status=OrderStatus.OPEN,
        price=price,
        quantity=quantity,
        remaining_quantity=quantity,
        reserved_amount=reserved_amount,
    )
    session.add(order)

    wallet.available_balance -= reserved_amount
    wallet.locked_balance += reserved_amount

    session.add_all(
        [
            LedgerEntry(
                transaction_id=transaction.id,
                wallet_id=wallet.id,
                entry_type=LedgerEntryType.DEBIT,
                balance_bucket=BalanceBucket.AVAILABLE,
                amount=reserved_amount,
                sequence=1,
                description="Reserve from available balance",
            ),
            LedgerEntry(
                transaction_id=transaction.id,
                wallet_id=wallet.id,
                entry_type=LedgerEntryType.CREDIT,
                balance_bucket=BalanceBucket.LOCKED,
                amount=reserved_amount,
                sequence=2,
                description="Reserve into locked balance",
            ),
        ]
    )

    await session.commit()
    await session.refresh(order)

    return OrderReservationResult(
        order=order,
        base_asset=base_asset,
        quote_asset=quote_asset,
        reserve_asset=reserve_asset,
        replayed=False,
    )


class OrderNotFoundError(OrderServiceError):
    pass


class OrderNotCancelableError(OrderServiceError):
    pass


class OrderReservationStateError(OrderServiceError):
    pass


@dataclass(frozen=True)
class OrderCancellationResult:
    order: Order
    reserve_asset: Asset
    replayed: bool


async def cancel_order_reservation(
    session: AsyncSession,
    *,
    user_id: UUID,
    order_id: UUID,
) -> OrderCancellationResult:
    order = await session.scalar(
        select(Order)
        .where(
            Order.id == order_id,
            Order.user_id == user_id,
        )
        .with_for_update()
    )
    if order is None:
        raise OrderNotFoundError(f"Order {order_id} was not found.")

    reserve_asset_id = (
        order.quote_asset_id if order.side == OrderSide.BUY else order.base_asset_id
    )
    reserve_asset = await session.scalar(
        select(Asset).where(Asset.id == reserve_asset_id)
    )
    if reserve_asset is None:
        raise OrderReservationStateError("Reserved asset was not found.")

    if order.status == OrderStatus.CANCELED:
        return OrderCancellationResult(
            order=order,
            reserve_asset=reserve_asset,
            replayed=True,
        )
    if order.status != OrderStatus.OPEN:
        raise OrderNotCancelableError(
            f"Only open orders can be canceled; current status is {order.status.value}."
        )

    wallet = await session.scalar(
        select(Wallet)
        .where(
            Wallet.owner_type == WalletOwnerType.USER,
            Wallet.user_id == user_id,
            Wallet.asset_id == reserve_asset.id,
        )
        .with_for_update()
    )
    if wallet is None or wallet.locked_balance < order.reserved_amount:
        raise OrderReservationStateError(
            "Locked balance does not cover the order reservation."
        )

    transaction = LedgerTransaction(
        reference=f"REL-{uuid4().hex[:20].upper()}",
        transaction_type=LedgerTransactionType.ORDER_RELEASE,
        status=LedgerTransactionStatus.POSTED,
        description=(
            f"Release {order.reserved_amount} {reserve_asset.code} for order {order.id}"
        ),
    )
    session.add(transaction)
    await session.flush()

    wallet.locked_balance -= order.reserved_amount
    wallet.available_balance += order.reserved_amount
    order.status = OrderStatus.CANCELED

    session.add_all(
        [
            LedgerEntry(
                transaction_id=transaction.id,
                wallet_id=wallet.id,
                entry_type=LedgerEntryType.DEBIT,
                balance_bucket=BalanceBucket.LOCKED,
                amount=order.reserved_amount,
                sequence=1,
                description="Release from locked balance",
            ),
            LedgerEntry(
                transaction_id=transaction.id,
                wallet_id=wallet.id,
                entry_type=LedgerEntryType.CREDIT,
                balance_bucket=BalanceBucket.AVAILABLE,
                amount=order.reserved_amount,
                sequence=2,
                description="Return to available balance",
            ),
        ]
    )

    await session.commit()
    await session.refresh(order)

    return OrderCancellationResult(
        order=order,
        reserve_asset=reserve_asset,
        replayed=False,
    )
