"""RabbitMQ publisher for durable transactional-outbox events."""

from __future__ import annotations

import json
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import (
    AbstractExchange,
    AbstractRobustChannel,
    AbstractRobustConnection,
)

from app.core.config import Settings
from app.models.outbox import OutboxEvent


class RabbitMQOutboxPublisher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractRobustChannel | None = None
        self._exchange: AbstractExchange | None = None

    async def __aenter__(self) -> RabbitMQOutboxPublisher:
        self._connection = await aio_pika.connect_robust(self._settings.rabbitmq_url)
        self._channel = await self._connection.channel(publisher_confirms=True)
        self._exchange = await self._channel.declare_exchange(
            self._settings.RABBITMQ_EVENTS_EXCHANGE,
            ExchangeType.TOPIC,
            durable=True,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        if self._connection is not None:
            await self._connection.close()
        self._connection = None
        self._channel = None
        self._exchange = None

    async def publish(self, event: OutboxEvent) -> None:
        if self._exchange is None:
            raise RuntimeError("RabbitMQ outbox publisher has not been started.")

        body = {
            "event_id": str(event.id),
            "event_type": event.event_type,
            "event_key": event.event_key,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
            "occurred_at": event.created_at.isoformat(),
            "payload": event.payload,
        }
        message = Message(
            body=json.dumps(
                body,
                separators=(",", ":"),
                sort_keys=True,
            ).encode(),
            content_type="application/json",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=str(event.id),
            type=event.event_type,
            headers={
                "event_key": event.event_key,
                "aggregate_type": event.aggregate_type,
            },
        )
        await self._exchange.publish(message, routing_key=event.event_type)
