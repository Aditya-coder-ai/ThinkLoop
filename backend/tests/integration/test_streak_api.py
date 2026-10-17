"""Integration tests for Streak Calendar, Heatmap API, and Rollup Job (Phase 10)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_clock, get_db, get_jwks_service, get_redis
from app.config import Settings, get_settings
from app.core.activity import record_activity
from app.core.clock import FakeClock
from app.core.security import JWKSService
from app.db.base import Base
from app.jobs.streak_rollup import streak_rollup
from app.main import create_app


@pytest.fixture
async def streak_app(rsa_key_pair: dict[str, Any], tmp_path: Any):
    """Set up test app with test database, fakeredis, mock JWKS, and FakeClock."""
    db_file = tmp_path / "streak_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    test_settings = Settings(
        database_url=db_url,
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
        environment="test",
        feature_streak=True,
        streak_freeze_earn_days=7,
        streak_freeze_max_cap=2,
        streak_initial_freezes=1,
    )

    app = create_app(test_settings)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    initial_time = datetime(2026, 10, 17, 10, 0, 0, tzinfo=UTC)
    fake_clock = FakeClock(initial_time)

    jwks_service = JWKSService(
        jwks_url=test_settings.auth_jwks_url,
        ttl_seconds=3600,
    )
    jwks_service.set_cached_keys(rsa_key_pair["jwks"])

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_jwks_service] = lambda: jwks_service
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_clock] = lambda: fake_clock

    yield {
        "app": app,
        "engine": engine,
        "session_factory": session_factory,
        "settings": test_settings,
        "fake_clock": fake_clock,
    }

    await engine.dispose()
    await fake_redis.aclose()


@pytest.mark.asyncio
async def test_feature_flag_disabled(streak_app: dict[str, Any], token_factory: Any) -> None:
    """When FEATURE_STREAK is disabled, /streak endpoints return HTTP 404."""
    app = streak_app["app"]
    disabled_settings = Settings(
        database_url=str(streak_app["settings"].database_url),
        redis_url="redis://localhost:6379/0",
        auth_jwks_url="https://auth.thinkloop.ai/.well-known/jwks.json",
        auth_issuer="https://auth.thinkloop.ai",
        auth_audience="thinkloop-api",
        environment="test",
        feature_streak=False,
    )
    app.dependency_overrides[get_settings] = lambda: disabled_settings

    token = token_factory(auth_id="auth0|user_flag_test", email="flag@example.com")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/streak", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "FEATURE_DISABLED"

        resp_cal = await client.get(
            "/streak/calendar?month=2026-10", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp_cal.status_code == 404

        resp_sum = await client.get(
            "/streak/summary?days=30", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp_sum.status_code == 404


@pytest.mark.asyncio
async def test_streak_progression_and_at_risk(
    streak_app: dict[str, Any], token_factory: Any
) -> None:
    """Test streak lifecycle: initial -> active today -> next day at-risk -> streak extension."""
    app = streak_app["app"]
    fake_clock: FakeClock = streak_app["fake_clock"]
    session_factory = streak_app["session_factory"]

    token = token_factory(auth_id="auth0|learner_streak_1", email="learner1@example.com")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Initial streak should be 0
        resp = await client.get("/streak", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["current"] == 0
        assert data["longest"] == 0
        assert data["freezes_available"] == 1
        assert data["today_active"] is False
        assert data["at_risk"] is False

        # Get user id by querying me endpoint
        me_resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        user_id = uuid.UUID(me_resp.json()["id"])

        # 2. Record qualifying activity on Day 1 (2026-10-17)
        async with session_factory() as session:
            await record_activity(
                session=session,
                user_id=user_id,
                kind="tutor_turn_gradable",
                ref_id="turn-1",
                clock=fake_clock,
            )

        resp2 = await client.get("/streak", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["current"] == 1
        assert data2["longest"] == 1
        assert data2["today_active"] is True
        assert data2["at_risk"] is False
        assert data2["last_active_date"] == "2026-10-17"

        # 3. Advance clock by 1 day (to 2026-10-18)
        fake_clock.advance(timedelta(days=1))

        # Today (Oct 18) not yet active, yesterday was active -> at_risk is True
        resp3 = await client.get("/streak", headers={"Authorization": f"Bearer {token}"})
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert data3["current"] == 1
        assert data3["longest"] == 1
        assert data3["today_active"] is False
        assert data3["at_risk"] is True

        # 4. Record qualifying activity on Day 2 (Oct 18)
        async with session_factory() as session:
            await record_activity(
                session=session,
                user_id=user_id,
                kind="focus_completed",
                ref_id="focus-1",
                meta={"duration_minutes": 25},
                clock=fake_clock,
            )

        resp4 = await client.get("/streak", headers={"Authorization": f"Bearer {token}"})
        assert resp4.status_code == 200
        data4 = resp4.json()
        assert data4["current"] == 2
        assert data4["longest"] == 2
        assert data4["today_active"] is True
        assert data4["at_risk"] is False


@pytest.mark.asyncio
async def test_user_isolation(streak_app: dict[str, Any], token_factory: Any) -> None:
    """User A's activities must not affect User B's streak."""
    app = streak_app["app"]
    fake_clock: FakeClock = streak_app["fake_clock"]
    session_factory = streak_app["session_factory"]

    token_a = token_factory(auth_id="auth0|user_a", email="usera@example.com")
    token_b = token_factory(auth_id="auth0|user_b", email="userb@example.com")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        me_a = await client.get("/me", headers={"Authorization": f"Bearer {token_a}"})
        user_a_id = uuid.UUID(me_a.json()["id"])

        # Record activity for User A
        async with session_factory() as session:
            await record_activity(
                session=session,
                user_id=user_a_id,
                kind="tutor_turn_gradable",
                ref_id="turn-a1",
                clock=fake_clock,
            )

        resp_a = await client.get("/streak", headers={"Authorization": f"Bearer {token_a}"})
        assert resp_a.json()["current"] == 1

        # User B should still have 0 streak
        resp_b = await client.get("/streak", headers={"Authorization": f"Bearer {token_b}"})
        assert resp_b.json()["current"] == 0
        assert resp_b.json()["today_active"] is False


@pytest.mark.asyncio
async def test_calendar_and_summary_endpoints(
    streak_app: dict[str, Any], token_factory: Any
) -> None:
    """Test calendar heatmap and summary series endpoints."""
    app = streak_app["app"]
    fake_clock: FakeClock = streak_app["fake_clock"]
    session_factory = streak_app["session_factory"]

    token = token_factory(auth_id="auth0|learner_cal", email="cal@example.com")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        me = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        user_id = uuid.UUID(me.json()["id"])

        # Log 40 minutes focus session today (level 3: 31-60 mins)
        async with session_factory() as session:
            await record_activity(
                session=session,
                user_id=user_id,
                kind="focus_completed",
                ref_id="focus-long",
                meta={"duration_minutes": 40},
                clock=fake_clock,
            )

        # GET /streak/calendar for 2026-10
        cal_resp = await client.get(
            "/streak/calendar?month=2026-10", headers={"Authorization": f"Bearer {token}"}
        )
        assert cal_resp.status_code == 200
        days = cal_resp.json()
        assert len(days) == 31  # October has 31 days

        day_17 = next(d for d in days if d["date"] == "2026-10-17")
        assert day_17["minutes"] == 40
        assert day_17["level"] == 3
        assert day_17["is_qualifying"] is True
        assert day_17["freeze_used"] is False

        # Invalid month format returns 422
        bad_cal = await client.get(
            "/streak/calendar?month=2026-13", headers={"Authorization": f"Bearer {token}"}
        )
        assert bad_cal.status_code == 422

        # GET /streak/summary?days=14
        sum_resp = await client.get(
            "/streak/summary?days=14", headers={"Authorization": f"Bearer {token}"}
        )
        assert sum_resp.status_code == 200
        summary = sum_resp.json()
        assert summary["days"] == 14
        assert summary["total_active_days"] == 1
        assert summary["total_minutes"] == 40
        assert summary["current_streak"] == 1
        assert len(summary["series"]) == 14


@pytest.mark.asyncio
async def test_streak_rollup_idempotency_and_auto_freeze(
    streak_app: dict[str, Any], token_factory: Any
) -> None:
    """Test nightly Arq job streak_rollup with idempotency and auto-freeze logic."""
    app = streak_app["app"]
    fake_clock: FakeClock = streak_app["fake_clock"]
    session_factory = streak_app["session_factory"]
    settings = streak_app["settings"]

    token = token_factory(auth_id="auth0|rollup_user", email="rollup@example.com")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        me = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
        user_id = uuid.UUID(me.json()["id"])

    # Day 1: 2026-10-15 (active)
    day1 = date(2026, 10, 15)
    async with session_factory() as session:
        await record_activity(
            session=session,
            user_id=user_id,
            kind="tutor_turn_gradable",
            ref_id="turn-r1",
            occurred_at=datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC),
        )
        # Rollup Day 1
        act1 = await streak_rollup(
            session=session,
            user_id=user_id,
            target_date=day1,
            clock=fake_clock,
            settings=settings,
        )
        assert act1.is_qualifying is True
        assert act1.freeze_applied is False

    # Day 2: 2026-10-16 (missed -> auto-freeze applied!)
    day2 = date(2026, 10, 16)
    async with session_factory() as session:
        act2 = await streak_rollup(
            session=session,
            user_id=user_id,
            target_date=day2,
            clock=fake_clock,
            settings=settings,
        )
        assert act2.is_qualifying is False
        assert act2.freeze_applied is True

    # Rerun Day 2 rollup -> check idempotency (no double-decrement)
    async with session_factory() as session:
        act2_repeat = await streak_rollup(
            session=session,
            user_id=user_id,
            target_date=day2,
            clock=fake_clock,
            settings=settings,
        )
        assert act2_repeat.freeze_applied is True

    # Day 3: 2026-10-17 (missed -> cannot freeze two consecutive days, streak breaks!)
    day3 = date(2026, 10, 17)
    async with session_factory() as session:
        act3 = await streak_rollup(
            session=session,
            user_id=user_id,
            target_date=day3,
            clock=fake_clock,
            settings=settings,
        )
        assert act3.is_qualifying is False
        assert act3.freeze_applied is False  # Cannot freeze consecutive!

    # Verify streak endpoint reflects freeze on day 2 (at_risk on day 3)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/streak", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["current"] == 2  # Maintained by day 2 freeze
        assert data["at_risk"] is True
        assert data["freezes_available"] == 0  # Used 1 freeze

    # Advance clock to Day 4 (2026-10-18): Day 3 missed and couldn't be frozen, so streak is broken
    fake_clock.advance(timedelta(days=1))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/streak", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["current"] == 0  # Broken after day 3 ended with no consecutive freeze
        assert data["longest"] == 2  # Day 1 active + Day 2 frozen = 2
        assert data["at_risk"] is False
