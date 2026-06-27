import asyncio
from uuid import uuid4

from sqlalchemy import select

from app.db.session import AsyncSessionFactory, engine
from app.models.outbox import OutboxEvent
from app.services.outbox import enqueue_outbox_event, publish_next_outbox_event


def test_outbox_delivery_marks_success_and_records_failure() -> None:
    asyncio.run(exercise_outbox_delivery())


async def exercise_outbox_delivery() -> None:
    try:
        success_id = uuid4()
        delivered_keys: list[str] = []

        async def successful_publisher(event: OutboxEvent) -> None:
            delivered_keys.append(event.event_key)

        async def failing_publisher(_: OutboxEvent) -> None:
            raise RuntimeError("broker unavailable")

        async with AsyncSessionFactory() as session:
            success_event = await enqueue_outbox_event(
                session,
                event_type="test.published",
                aggregate_type="test",
                aggregate_id=success_id,
                payload={"result": "success"},
            )
            await session.commit()

        async with AsyncSessionFactory() as session:
            published = await publish_next_outbox_event(
                session,
                publisher=successful_publisher,
                event_id=success_event.id,
            )
            stored_success = await session.scalar(
                select(OutboxEvent).where(OutboxEvent.id == success_event.id)
            )
            no_more_events = await publish_next_outbox_event(
                session,
                publisher=successful_publisher,
                event_id=success_event.id,
            )

        assert published is True
        assert delivered_keys == [success_event.event_key]
        assert stored_success is not None
        assert stored_success.published_at is not None
        assert stored_success.publish_attempts == 1
        assert stored_success.last_error is None
        assert no_more_events is False

        async with AsyncSessionFactory() as session:
            failure_event = await enqueue_outbox_event(
                session,
                event_type="test.failed",
                aggregate_type="test",
                aggregate_id=uuid4(),
                payload={"result": "failure"},
            )
            await session.commit()

        async with AsyncSessionFactory() as session:
            published = await publish_next_outbox_event(
                session,
                publisher=failing_publisher,
                event_id=failure_event.id,
            )
            stored_failure = await session.scalar(
                select(OutboxEvent).where(OutboxEvent.id == failure_event.id)
            )

        assert published is False
        assert stored_failure is not None
        assert stored_failure.published_at is None
        assert stored_failure.publish_attempts == 1
        assert stored_failure.last_error == "broker unavailable"
    finally:
        await engine.dispose()
