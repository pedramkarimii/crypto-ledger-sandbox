import asyncio
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import AsyncSessionFactory, engine
from app.models.enums import OrderSide
from app.models.outbox import OutboxEvent
from app.models.user import User
from app.scripts.seed_dev_data import main as seed_development_data
from app.services.ledger import post_sandbox_funding
from app.services.orders import (
    cancel_order_reservation,
    create_order_reservation,
)


def test_order_lifecycle_writes_outbox_events_once() -> None:
    asyncio.run(exercise_order_lifecycle_outbox())


async def exercise_order_lifecycle_outbox() -> None:
    try:
        await seed_development_data()

        async with AsyncSessionFactory() as session:
            user = User(
                email=f"outbox-order-{uuid4().hex}@example.com",
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
                idempotency_key=f"outbox-funding-{uuid4().hex}",
            )

            reservation = await create_order_reservation(
                session,
                user_id=user.id,
                base_asset_code="BTC",
                quote_asset_code="USDT",
                side=OrderSide.BUY,
                price=Decimal("20000"),
                quantity=Decimal("0.001"),
                idempotency_key=f"outbox-order-{uuid4().hex}",
            )
            replay = await create_order_reservation(
                session,
                user_id=user.id,
                base_asset_code="BTC",
                quote_asset_code="USDT",
                side=OrderSide.BUY,
                price=Decimal("20000"),
                quantity=Decimal("0.001"),
                idempotency_key=reservation.order.idempotency_key,
            )
            cancellation = await cancel_order_reservation(
                session,
                user_id=user.id,
                order_id=reservation.order.id,
            )
            cancellation_replay = await cancel_order_reservation(
                session,
                user_id=user.id,
                order_id=reservation.order.id,
            )
            events = (
                await session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.aggregate_id == reservation.order.id)
                    .order_by(OutboxEvent.event_type)
                )
            ).all()

            assert replay.replayed is True
            assert cancellation.replayed is False
            assert cancellation_replay.replayed is True
            assert [event.event_type for event in events] == [
                "order.canceled",
                "order.created",
            ]
            assert events[0].event_key == f"order.canceled:{reservation.order.id}"
            assert events[0].payload["status"] == "canceled"
            assert events[1].event_key == f"order.created:{reservation.order.id}"
            assert events[1].payload["status"] == "open"
            assert events[1].payload["base_asset_code"] == "BTC"
            assert events[1].payload["quote_asset_code"] == "USDT"
            assert Decimal(events[1].payload["reserved_amount"]) == Decimal("20")
            assert all(event.published_at is None for event in events)
            assert all(event.publish_attempts == 0 for event in events)
    finally:
        await engine.dispose()
