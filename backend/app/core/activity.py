"""Idempotent activity event recording service."""

import logging
import uuid
import zoneinfo
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.db.models import ActivityEvent, UserPreferences

logger = logging.getLogger(__name__)


def compute_local_date(occurred_at: datetime, timezone_str: str) -> date:
    """Compute local date from a UTC timestamp and an IANA timezone identifier."""
    try:
        tz = zoneinfo.ZoneInfo(timezone_str)
    except Exception:
        tz = zoneinfo.ZoneInfo("UTC")
    return occurred_at.astimezone(tz).date()


async def record_activity(
    session: AsyncSession,
    user_id: uuid.UUID,
    kind: str,
    ref_id: str,
    ref_type: str | None = None,
    occurred_at: datetime | None = None,
    meta: dict[str, Any] | None = None,
    user_timezone: str | None = None,
    clock: Clock | None = None,
) -> ActivityEvent:
    """Record an activity event idempotently.

    If an event with the same (user_id, kind, ref_id) already exists, returns the existing
    event without error. Computes local_date using the user's timezone at event time.
    """
    if clock is None:
        clock = SystemClock()

    if occurred_at is None:
        occurred_at = clock.now()
    elif occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    else:
        occurred_at = occurred_at.astimezone(UTC)

    # Resolve user timezone if not explicitly provided
    if user_timezone is None:
        pref_query = select(UserPreferences.timezone).where(UserPreferences.user_id == user_id)
        pref_result = await session.execute(pref_query)
        pref_tz = pref_result.scalar_one_or_none()
        user_timezone = pref_tz or "UTC"

    local_date = compute_local_date(occurred_at, user_timezone)

    # Check for existing event (idempotency check)
    existing_query = select(ActivityEvent).where(
        ActivityEvent.user_id == user_id,
        ActivityEvent.kind == kind,
        ActivityEvent.ref_id == ref_id,
    )
    result = await session.execute(existing_query)
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    event = ActivityEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        kind=kind,
        ref_type=ref_type,
        ref_id=ref_id,
        occurred_at=occurred_at,
        local_date=local_date,
        meta=meta or {},
    )

    try:
        async with session.begin_nested():
            session.add(event)
            await session.flush()
    except IntegrityError:
        # Concurrent insert occurred, re-query existing
        result = await session.execute(existing_query)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        raise

    logger.info(
        "Recorded activity event",
        extra={
            "user_id": str(user_id),
            "kind": kind,
            "ref_id": ref_id,
            "local_date": str(local_date),
        },
    )
    return event
