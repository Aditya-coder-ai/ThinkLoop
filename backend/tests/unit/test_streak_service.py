"""Unit tests for StreakService business logic (Phase 10)."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.core.clock import FakeClock
from app.db.base import Base
from app.db.models import ActivityEvent, DailyActivity, User, UserPreferences
from app.services.streak import StreakService


@pytest.fixture
async def streak_db(tmp_path: Any):
    """Create test SQLite database and yield session."""
    db_file = tmp_path / "streak_service_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        yield session

    await engine.dispose()


def test_compute_intensity_level() -> None:
    """compute_intensity_level maps study minutes and freeze states to 0-4."""
    service = StreakService(
        session=None,  # type: ignore[arg-type]
        settings=Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url="redis://localhost:6379/0",
            auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
            auth_issuer="https://auth.thinkloop.ai",
            auth_audience="thinkloop-api",
        ),
        clock=FakeClock(datetime(2026, 10, 17, tzinfo=UTC)),
    )

    # Freeze applied -> always level 1
    assert service.compute_intensity_level(minutes=0, is_qualifying=False, freeze_applied=True) == 1

    # Inactive 0 minutes -> level 0
    assert (
        service.compute_intensity_level(minutes=0, is_qualifying=False, freeze_applied=False) == 0
    )

    # 1 to 15 mins -> level 1
    assert (
        service.compute_intensity_level(minutes=15, is_qualifying=True, freeze_applied=False) == 1
    )

    # 16 to 30 mins -> level 2
    assert (
        service.compute_intensity_level(minutes=25, is_qualifying=True, freeze_applied=False) == 2
    )

    # 31 to 60 mins -> level 3
    assert (
        service.compute_intensity_level(minutes=45, is_qualifying=True, freeze_applied=False) == 3
    )

    # > 60 mins -> level 4
    assert (
        service.compute_intensity_level(minutes=90, is_qualifying=True, freeze_applied=False) == 4
    )


def test_evaluate_day_qualifying_rules() -> None:
    """evaluate_day_qualifying recognizes various learning events."""
    service = StreakService(
        session=None,  # type: ignore[arg-type]
        settings=Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url="redis://localhost:6379/0",
            auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
            auth_issuer="https://auth.thinkloop.ai",
            auth_audience="thinkloop-api",
            streak_min_focus_minutes=10,
            streak_min_tutor_turns=1,
        ),
        clock=FakeClock(datetime(2026, 10, 17, tzinfo=UTC)),
    )

    # Empty events -> not qualifying
    is_q, mins, counts = service.evaluate_day_qualifying([])
    assert is_q is False
    assert mins == 0
    assert counts == {}

    # Event with explicit duration_minutes
    ev1 = ActivityEvent(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        kind="focus_completed",
        ref_id="f1",
        occurred_at=datetime(2026, 10, 17, 10, 0, 0, tzinfo=UTC),
        local_date=date(2026, 10, 17),
        meta={"duration_minutes": 25},
    )
    is_q1, mins1, counts1 = service.evaluate_day_qualifying([ev1])
    assert is_q1 is True
    assert mins1 == 25
    assert counts1["focus_completed"] == 1

    # Event with focus_completed but no meta minutes -> falls back to min focus minutes
    ev2 = ActivityEvent(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        kind="focus_completed",
        ref_id="f2",
        occurred_at=datetime(2026, 10, 17, 10, 0, 0, tzinfo=UTC),
        local_date=date(2026, 10, 17),
        meta={},
    )
    is_q2, mins2, _ = service.evaluate_day_qualifying([ev2])
    assert is_q2 is True
    assert mins2 == 10

    # Review, battle, doubt, flashcard, voice session
    for kind in (
        "review_completed",
        "battle_completed",
        "flashcard_reviewed",
        "doubt_resolved",
        "voice_session",
    ):
        ev = ActivityEvent(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            kind=kind,
            ref_id=f"ref-{kind}",
            occurred_at=datetime(2026, 10, 17, 10, 0, 0, tzinfo=UTC),
            local_date=date(2026, 10, 17),
            meta={},
        )
        is_q_kind, mins_kind, counts_kind = service.evaluate_day_qualifying([ev])
        assert is_q_kind is True
        assert mins_kind == 2
        assert counts_kind[kind] == 1


@pytest.mark.asyncio
async def test_get_or_create_state_and_timezone(streak_db: AsyncSession) -> None:
    """StreakService retrieves or initializes state and reads user timezone."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
        streak_initial_freezes=2,
    )
    service = StreakService(
        session=streak_db,
        settings=settings,
        clock=FakeClock(datetime(2026, 10, 17, tzinfo=UTC)),
    )

    user = User(auth_id="auth0|service_test_user", email="service@example.com")
    streak_db.add(user)
    await streak_db.commit()

    # Timezone defaults to UTC when no preferences set
    tz_default = await service.get_user_timezone(user.id)
    assert tz_default == "UTC"

    # Add preferences with custom timezone
    pref = UserPreferences(user_id=user.id, timezone="Asia/Kolkata")
    streak_db.add(pref)
    await streak_db.commit()

    tz_custom = await service.get_user_timezone(user.id)
    assert tz_custom == "Asia/Kolkata"

    # Creates streak state on first call
    state1 = await service.get_or_create_streak_state(user.id)
    assert state1.freezes_available == 2
    assert state1.longest_streak == 0

    # Returns same state on subsequent call
    state2 = await service.get_or_create_streak_state(user.id)
    assert state2.id == state1.id


@pytest.mark.asyncio
async def test_get_calendar_and_summary_service_methods(streak_db: AsyncSession) -> None:
    """Test get_calendar and get_summary_series service methods directly."""
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
    )
    service = StreakService(
        session=streak_db,
        settings=settings,
        clock=FakeClock(datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC)),
    )

    user = User(auth_id="auth0|cal_service_user", email="calservice@example.com")
    streak_db.add(user)
    await streak_db.commit()

    # Seed daily activity for 2026-10-15
    day_activity = DailyActivity(
        user_id=user.id,
        local_date=date(2026, 10, 15),
        minutes=35,
        counts={"focus_completed": 1},
        is_qualifying=True,
        freeze_applied=False,
    )
    streak_db.add(day_activity)

    # Seed an unrolled ActivityEvent for 2026-10-16
    event = ActivityEvent(
        id=uuid.uuid4(),
        user_id=user.id,
        kind="tutor_turn_gradable",
        ref_id="turn-seed-1",
        occurred_at=datetime(2026, 10, 16, 10, 0, 0, tzinfo=UTC),
        local_date=date(2026, 10, 16),
        meta={},
    )
    streak_db.add(event)
    await streak_db.commit()

    # Call get_calendar for October 2026 (today is 2026-10-17)
    cal = await service.get_calendar(
        user_id=user.id,
        year=2026,
        month=10,
        today=date(2026, 10, 17),
    )
    assert len(cal) == 31

    day_15 = next(d for d in cal if d.date == date(2026, 10, 15))
    assert day_15.minutes == 35
    assert day_15.is_qualifying is True
    assert day_15.level == 3

    day_16 = next(d for d in cal if d.date == date(2026, 10, 16))
    assert day_16.is_qualifying is True
    assert day_16.level == 1

    # Future day (Oct 25)
    day_25 = next(d for d in cal if d.date == date(2026, 10, 25))
    assert day_25.level == 0
    assert day_25.is_qualifying is False

    # Call get_summary_series for 7 days
    summary_series = await service.get_summary_series(
        user_id=user.id,
        days=7,
        today=date(2026, 10, 17),
    )
    assert summary_series.days == 7
    assert summary_series.total_active_days == 2  # Oct 15 and Oct 16
    assert summary_series.total_minutes == 37  # 35 + 2
    assert summary_series.current_streak == 2
