"""Arq background job for nightly daily_activity rollups and streak maintenance (Phase 10)."""

import uuid
from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.clock import Clock, SystemClock
from app.db.models import ActivityEvent, DailyActivity
from app.services.streak import StreakService


async def streak_rollup(
    session: AsyncSession,
    user_id: uuid.UUID,
    target_date: date,
    clock: Clock | None = None,
    settings: Settings | None = None,
) -> DailyActivity:
    """Materialize daily activity for user_id on target_date, auto-applying freezes if missed.

    Idempotent: repeating for the same user_id and target_date produces identical state.
    """
    if clock is None:
        clock = SystemClock()
    if settings is None:
        settings = get_settings()

    service = StreakService(session=session, settings=settings, clock=clock)
    state = await service.get_or_create_streak_state(user_id)

    # 1. Fetch events for this date
    stmt = select(ActivityEvent).where(
        and_(
            ActivityEvent.user_id == user_id,
            ActivityEvent.local_date == target_date,
        )
    )
    res = await session.execute(stmt)
    events = list(res.scalars().all())

    is_qualifying, total_minutes, counts = service.evaluate_day_qualifying(events)

    # 2. Check existing DailyActivity row
    daily_stmt = select(DailyActivity).where(
        and_(
            DailyActivity.user_id == user_id,
            DailyActivity.local_date == target_date,
        )
    )
    daily_res = await session.execute(daily_stmt)
    daily_row = daily_res.scalar_one_or_none()

    freeze_applied = False
    if daily_row and daily_row.freeze_applied:
        freeze_applied = True

    target_iso = target_date.isoformat()
    if not is_qualifying and not freeze_applied and target_iso not in state.freezes_used_dates:
        # Check if user had an active streak ending at target_date - 1
        day_before = target_date - timedelta(days=1)
        prev_stmt = select(DailyActivity).where(
            and_(
                DailyActivity.user_id == user_id,
                DailyActivity.local_date == day_before,
            )
        )
        prev_res = await session.execute(prev_stmt)
        prev_row = prev_res.scalar_one_or_none()

        can_freeze = (
            prev_row is not None
            and (prev_row.is_qualifying or prev_row.freeze_applied)
            and not prev_row.freeze_applied
            and state.freezes_available > 0
        )

        if can_freeze:
            freeze_applied = True
            state.freezes_available -= 1
            state.freezes_used_dates = [*state.freezes_used_dates, target_iso]

    # 3. Upsert DailyActivity
    if daily_row is None:
        daily_row = DailyActivity(
            user_id=user_id,
            local_date=target_date,
            minutes=total_minutes,
            counts=counts,
            is_qualifying=is_qualifying,
            freeze_applied=freeze_applied,
        )
        session.add(daily_row)
    else:
        daily_row.minutes = total_minutes
        daily_row.counts = counts
        daily_row.is_qualifying = is_qualifying
        daily_row.freeze_applied = freeze_applied

    await session.flush()

    # 4. Check if a freeze was earned on this day
    # Recalculate streak summary up to target_date
    summary = await service.get_streak_summary(user_id=user_id, today=target_date)
    if (
        summary.current > 0
        and (summary.current % settings.streak_freeze_earn_days == 0)
        and state.freezes_available < settings.streak_freeze_max_cap
    ):
        state.freezes_available = min(state.freezes_available + 1, settings.streak_freeze_max_cap)

    await session.commit()
    return daily_row
