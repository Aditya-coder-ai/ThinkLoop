"""Unit tests for authoritative Clock protocol and implementations."""

from datetime import UTC, datetime, timedelta

from app.core.clock import Clock, FakeClock, SystemClock


def test_system_clock_returns_utc_aware_datetime() -> None:
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo is not None
    assert now.tzinfo == UTC
    assert isinstance(clock, Clock)


def test_fake_clock_default_initialization() -> None:
    clock = FakeClock()
    assert clock.now() == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert isinstance(clock, Clock)


def test_fake_clock_custom_initialization() -> None:
    naive_dt = datetime(2026, 6, 15, 10, 30, 0)
    clock = FakeClock(naive_dt)
    assert clock.now() == datetime(2026, 6, 15, 10, 30, 0, tzinfo=UTC)


def test_fake_clock_advance() -> None:
    clock = FakeClock(datetime(2026, 3, 1, 0, 0, 0, tzinfo=UTC))
    new_time = clock.advance(timedelta(hours=2, minutes=30))
    assert new_time == datetime(2026, 3, 1, 2, 30, 0, tzinfo=UTC)
    assert clock.now() == datetime(2026, 3, 1, 2, 30, 0, tzinfo=UTC)


def test_fake_clock_set_time() -> None:
    clock = FakeClock()
    target = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
    clock.set_time(target)
    assert clock.now() == target
