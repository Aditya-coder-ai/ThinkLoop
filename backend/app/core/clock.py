"""Authoritative Clock protocol and implementations for time-dependent operations."""

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Protocol defining the time source interface."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC datetime."""
        ...


class SystemClock:
    """Production clock returning system UTC time."""

    def now(self) -> datetime:
        """Return authoritative server UTC time."""
        return datetime.now(UTC)


class FakeClock:
    """Deterministic, settable, and advanceable clock for testing and simulation."""

    def __init__(self, initial_time: datetime | None = None) -> None:
        if initial_time is None:
            self._now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        elif initial_time.tzinfo is None:
            self._now = initial_time.replace(tzinfo=UTC)
        else:
            self._now = initial_time.astimezone(UTC)

    def now(self) -> datetime:
        """Return the current simulated UTC time."""
        return self._now

    def set_time(self, new_time: datetime) -> None:
        """Explicitly set current simulated time."""
        if new_time.tzinfo is None:
            self._now = new_time.replace(tzinfo=UTC)
        else:
            self._now = new_time.astimezone(UTC)

    def advance(self, duration: timedelta) -> datetime:
        """Advance simulated time by the given duration and return new time."""
        self._now += duration
        return self._now
