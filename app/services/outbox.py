from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent


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
