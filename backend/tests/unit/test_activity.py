"""Unit tests for activity event recording, local_date calculation, and idempotency."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.activity import compute_local_date, record_activity
from app.core.clock import FakeClock
from app.db.base import Base
from app.db.models import User, UserPreferences


def test_compute_local_date_new_york_spring_forward_dst() -> None:
    # 2026-03-08 03:00 UTC is 2026-03-07 22:00 EST in New York
    dt_before_midnight = datetime(2026, 3, 8, 3, 0, 0, tzinfo=UTC)
    assert compute_local_date(dt_before_midnight, "America/New_York") == date(2026, 3, 7)

    # 2026-03-08 05:00 UTC is 2026-03-08 00:00 EST in New York
    dt_after_midnight = datetime(2026, 3, 8, 5, 0, 0, tzinfo=UTC)
    assert compute_local_date(dt_after_midnight, "America/New_York") == date(2026, 3, 8)

    # 2026-03-08 08:00 UTC is 2026-03-08 04:00 EDT (after spring-forward 2am->3am)
    dt_after_spring = datetime(2026, 3, 8, 8, 0, 0, tzinfo=UTC)
    assert compute_local_date(dt_after_spring, "America/New_York") == date(2026, 3, 8)


def test_compute_local_date_asia_kolkata_half_hour_offset() -> None:
    # 2026-01-01 18:00 UTC + 5:30 = 2026-01-01 23:30 IST -> date is 2026-01-01
    dt1 = datetime(2026, 1, 1, 18, 0, 0, tzinfo=UTC)
    assert compute_local_date(dt1, "Asia/Kolkata") == date(2026, 1, 1)

    # 2026-01-01 18:45 UTC + 5:30 = 2026-01-02 00:15 IST -> date rolls to 2026-01-02
    dt2 = datetime(2026, 1, 1, 18, 45, 0, tzinfo=UTC)
    assert compute_local_date(dt2, "Asia/Kolkata") == date(2026, 1, 2)


@pytest.mark.asyncio
async def test_record_activity_idempotency_and_fake_clock() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    clock = FakeClock(datetime(2026, 5, 1, 14, 0, 0, tzinfo=UTC))

    user_id = uuid.uuid4()
    async with session_factory() as session:
        user = User(id=user_id, auth_id="test_user_activity", email="act@example.com")
        prefs = UserPreferences(user_id=user_id, timezone="Asia/Kolkata")
        session.add_all([user, prefs])
        await session.commit()

    async with session_factory() as session:
        # First record
        event1 = await record_activity(
            session=session,
            user_id=user_id,
            kind="tutor_turn_gradable",
            ref_id="turn_abc_123",
            ref_type="turn",
            meta={"points": 10},
            clock=clock,
        )
        await session.commit()

        assert event1.kind == "tutor_turn_gradable"
        assert event1.ref_id == "turn_abc_123"
        # 14:00 UTC + 5:30 = 19:30 on 2026-05-01
        assert event1.local_date == date(2026, 5, 1)
        first_id = event1.id

        # Second record with identical (user_id, kind, ref_id) -> must be a no-op returning existing
        event2 = await record_activity(
            session=session,
            user_id=user_id,
            kind="tutor_turn_gradable",
            ref_id="turn_abc_123",
            ref_type="turn",
            clock=clock,
        )
        await session.commit()

        assert event2.id == first_id

        # Advance clock to next day
        clock.advance(timedelta(days=1, hours=6))
        # Now at 2026-05-02 20:00 UTC -> in Asia/Kolkata is 2026-05-03 01:30 IST!
        event3 = await record_activity(
            session=session,
            user_id=user_id,
            kind="focus_completed",
            ref_id="focus_xyz_999",
            ref_type="focus",
            clock=clock,
        )
        await session.commit()

        assert event3.kind == "focus_completed"
        assert event3.local_date == date(2026, 5, 3)

    await engine.dispose()
