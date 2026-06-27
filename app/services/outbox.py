from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent

OutboxPublisher = Callable[[OutboxEvent], Awaitable[None]]


async def enqueue_outbox_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict[str, Any],
) -> OutboxEvent:
    event = OutboxEvent(
        event_type=event_type,
        event_key=f"{event_type}:{aggregate_id}",
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )
    session.add(event)
    await session.flush()
    return event


async def publish_next_outbox_event(
    session: AsyncSession,
    *,
    publisher: OutboxPublisher,
    event_id: UUID | None = None,
) -> bool:
    statement = select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
    if event_id is not None:
        statement = statement.where(OutboxEvent.id == event_id)

    event = await session.scalar(
        statement.order_by(OutboxEvent.created_at, OutboxEvent.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if event is None:
        return False

    event.publish_attempts += 1
    try:
        await publisher(event)
    except Exception as exc:
        event.last_error = str(exc)[:2000]
        await session.commit()
        return False

    event.published_at = datetime.now(UTC)
    event.last_error = None
    await session.commit()
    return True
