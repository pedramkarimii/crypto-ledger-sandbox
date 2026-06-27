"""Continuously relay transactional-outbox events to RabbitMQ."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.db.session import AsyncSessionFactory, engine
from app.events.rabbitmq import RabbitMQOutboxPublisher
from app.services.outbox import publish_next_outbox_event

logger = logging.getLogger(__name__)


async def run_outbox_relay() -> None:
    settings = get_settings()

    async with RabbitMQOutboxPublisher(settings) as publisher:
        logger.info(
            "Outbox relay connected to RabbitMQ exchange %s.",
            settings.RABBITMQ_EVENTS_EXCHANGE,
        )
        while True:
            async with AsyncSessionFactory() as session:
                delivered = await publish_next_outbox_event(
                    session,
                    publisher=publisher.publish,
                )
            if not delivered:
                await asyncio.sleep(settings.OUTBOX_RELAY_POLL_SECONDS)


async def main() -> None:
    try:
        await run_outbox_relay()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
