import asyncio
import json
from uuid import uuid4

import aio_pika
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionFactory, engine
from app.events.rabbitmq import RabbitMQOutboxPublisher
from app.models.outbox import OutboxEvent
from app.services.outbox import enqueue_outbox_event, publish_next_outbox_event


def test_rabbitmq_publisher_delivers_a_durable_outbox_event() -> None:
    asyncio.run(exercise_rabbitmq_outbox_publisher())


async def exercise_rabbitmq_outbox_publisher() -> None:
    settings = get_settings()
    connection = None

    try:
        async with RabbitMQOutboxPublisher(settings) as publisher:
            connection = await aio_pika.connect_robust(settings.rabbitmq_url)
            channel = await connection.channel()
            queue = await channel.declare_queue(
                "",
                exclusive=True,
                auto_delete=True,
            )
            await queue.bind(
                settings.RABBITMQ_EVENTS_EXCHANGE,
                routing_key="test.published",
            )

            async with AsyncSessionFactory() as session:
                event = await enqueue_outbox_event(
                    session,
                    event_type="test.published",
                    aggregate_type="test",
                    aggregate_id=uuid4(),
                    payload={"result": "ok"},
                )
                await session.commit()

            async with AsyncSessionFactory() as session:
                delivered = await publish_next_outbox_event(
                    session,
                    publisher=publisher.publish,
                    event_id=event.id,
                )
                stored_event = await session.scalar(
                    select(OutboxEvent).where(OutboxEvent.id == event.id)
                )

            message = await queue.get(timeout=5, fail=True)
            try:
                body = json.loads(message.body)
            finally:
                await message.ack()

            assert delivered is True
            assert stored_event is not None
            assert stored_event.published_at is not None
            assert stored_event.publish_attempts == 1
            assert body["event_id"] == str(event.id)
            assert body["event_type"] == "test.published"
            assert body["event_key"] == event.event_key
            assert body["aggregate_type"] == "test"
            assert body["aggregate_id"] == str(event.aggregate_id)
            assert body["payload"] == {"result": "ok"}
    finally:
        if connection is not None:
            await connection.close()
        await engine.dispose()
