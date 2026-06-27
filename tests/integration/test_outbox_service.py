import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.db.session import AsyncSessionFactory, engine
from app.models.outbox import OutboxEvent
from app.services.outbox import enqueue_outbox_event


def test_enqueue_outbox_event_persists_a_pending_event() -> None:
    asyncio.run(exercise_enqueue_outbox_event())


async def exercise_enqueue_outbox_event() -> None:
    try:
        aggregate_id = uuid4()

        async with AsyncSessionFactory() as session:
            event = await enqueue_outbox_event(
                session,
                event_type="order.created",
                aggregate_type="order",
                aggregate_id=aggregate_id,
                payload={
                    "order_id": str(aggregate_id),
                    "side": "buy",
                    "reserved_amount": "20",
                },
            )
            await session.commit()

            stored_event = await session.scalar(
                select(OutboxEvent).where(OutboxEvent.id == event.id)
            )

        assert stored_event is not None
        assert stored_event.event_type == "order.created"
        assert stored_event.event_key == f"order.created:{aggregate_id}"
        assert stored_event.aggregate_type == "order"
        assert stored_event.aggregate_id == aggregate_id
        assert stored_event.payload["side"] == "buy"
        assert stored_event.published_at is None
        assert stored_event.publish_attempts == 0
        assert stored_event.last_error is None
    finally:
        await engine.dispose()
