"""Unit tests for the pure streak calculation engine (Phase 10)."""

from datetime import date, timedelta

import pytest

from app.core.streak_calc import StreakRules, StreakSummary, compute_streaks


def test_empty_active_dates() -> None:
    """Empty active dates should yield zero streaks."""
    today = date(2026, 10, 17)
    summary = compute_streaks(active_dates=set(), today=today)
    assert summary == StreakSummary(
        current=0,
        longest=0,
        last_active_date=None,
        at_risk=False,
        today_active=False,
    )


def test_single_day_today_active() -> None:
    """Active only today gives a current and longest streak of 1."""
    today = date(2026, 10, 17)
    summary = compute_streaks(active_dates={today}, today=today)
    assert summary.current == 1
    assert summary.longest == 1
    assert summary.last_active_date == today
    assert summary.today_active is True
    assert summary.at_risk is False


def test_today_not_active_yesterday_active() -> None:
    """If yesterday was active and today is not yet active, streak is intact but at risk."""
    today = date(2026, 10, 17)
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    summary = compute_streaks(
        active_dates={day_before, yesterday},
        today=today,
    )
    assert summary.current == 2
    assert summary.longest == 2
    assert summary.last_active_date == yesterday
    assert summary.today_active is False
    assert summary.at_risk is True


def test_two_day_gap_breaks_streak_without_freezes() -> None:
    """A missed day before yesterday breaks the streak."""
    today = date(2026, 10, 17)
    active = {date(2026, 10, 10), date(2026, 10, 11)}  # 6 days ago
    summary = compute_streaks(active_dates=active, today=today)
    assert summary.current == 0
    assert summary.longest == 2
    assert summary.last_active_date == date(2026, 10, 11)
    assert summary.today_active is False
    assert summary.at_risk is False


def test_freeze_covers_single_missed_day() -> None:
    """A freeze covers exactly one missed day in an ongoing streak."""
    today = date(2026, 10, 17)
    day1 = today - timedelta(days=3)  # Oct 14 (active)
    day2 = today - timedelta(days=2)  # Oct 15 (missed, frozen)
    day3 = today - timedelta(days=1)  # Oct 16 (active)
    day4 = today  # Oct 17 (active)

    summary = compute_streaks(
        active_dates={day1, day3, day4},
        today=today,
        freezes_used={day2},
    )
    assert summary.current == 4
    assert summary.longest == 4
    assert summary.today_active is True
    assert summary.at_risk is False


def test_freeze_covers_yesterday_at_risk() -> None:
    """A freeze on yesterday preserves the streak when today is not yet active."""
    today = date(2026, 10, 17)
    day1 = today - timedelta(days=2)  # active
    yesterday = today - timedelta(days=1)  # missed, frozen

    summary = compute_streaks(
        active_dates={day1},
        today=today,
        freezes_used={yesterday},
    )
    assert summary.current == 2
    assert summary.longest == 2
    assert summary.today_active is False
    assert summary.at_risk is True


def test_two_consecutive_freezes_forbidden() -> None:
    """Two consecutive freezes cannot bridge a 2-day gap; streak breaks on 2nd freeze."""
    today = date(2026, 10, 17)
    day1 = today - timedelta(days=4)  # Oct 13 active
    day2 = today - timedelta(days=3)  # Oct 14 frozen
    day3 = today - timedelta(days=2)  # Oct 15 frozen (consecutive!)
    day4 = today - timedelta(days=1)  # Oct 16 active
    day5 = today  # Oct 17 active

    summary = compute_streaks(
        active_dates={day1, day4, day5},
        today=today,
        freezes_used={day2, day3},
    )
    # The first run (Oct 13 + Oct 14 freeze) reached 2 days.
    # Oct 15 could not be frozen consecutively, breaking the streak.
    # The new run started on Oct 16, continuing to Oct 17 (length 2).
    assert summary.current == 2
    assert summary.longest == 2
    assert summary.today_active is True


def test_freeze_cannot_start_streak_without_prior_active() -> None:
    """A freeze on a day before any active date does not start a streak."""
    today = date(2026, 10, 17)
    freeze_day = today - timedelta(days=1)
    summary = compute_streaks(
        active_dates=set(),
        today=today,
        freezes_used={freeze_day},
    )
    assert summary.current == 0
    assert summary.longest == 0


def test_leap_day_streak() -> None:
    """Streak correctly crosses Feb 28 -> Feb 29 -> Mar 1 in leap year 2024."""
    today = date(2024, 3, 1)
    active = {date(2024, 2, 28), date(2024, 2, 29), date(2024, 3, 1)}
    summary = compute_streaks(active_dates=active, today=today)
    assert summary.current == 3
    assert summary.longest == 3
    assert summary.today_active is True


def test_month_and_year_boundaries() -> None:
    """Streak correctly crosses Dec 31 -> Jan 1 boundary."""
    today = date(2027, 1, 1)
    active = {date(2026, 12, 31), date(2027, 1, 1)}
    summary = compute_streaks(active_dates=active, today=today)
    assert summary.current == 2
    assert summary.longest == 2


def test_future_dates_ignored() -> None:
    """Dates in the future relative to today are ignored for safety."""
    today = date(2026, 10, 17)
    future = today + timedelta(days=1)
    summary = compute_streaks(active_dates={today, future}, today=today)
    assert summary.current == 1
    assert summary.longest == 1


@pytest.mark.parametrize(
    ("active_offsets", "freeze_offsets", "expected_current", "expected_longest"),
    [
        ([0], [], 1, 1),
        ([1], [], 1, 1),  # yesterday only -> at_risk, current=1
        ([0, 1, 2], [], 3, 3),
        ([0, 2], [1], 3, 3),  # 1 day freeze in middle
        ([0, 3], [1, 2], 1, 2),  # 2 consecutive freezes fail on day 1; run (3+2) is 2, today is 1
        ([1, 2, 4, 5, 6], [], 2, 3),  # longest is 3 (days 4, 5, 6), current is 2 (days 1, 2)
    ],
)
def test_table_driven_cases(
    active_offsets: list[int],
    freeze_offsets: list[int],
    expected_current: int,
    expected_longest: int,
) -> None:
    """Table-driven test suite for streak calculations based on offsets from today."""
    today = date(2026, 10, 17)
    active = {today - timedelta(days=o) for o in active_offsets}
    freezes = {today - timedelta(days=o) for o in freeze_offsets}

    summary = compute_streaks(active_dates=active, today=today, freezes_used=freezes)
    assert summary.current == expected_current
    assert summary.longest == expected_longest


def test_property_streak_never_exceeds_span() -> None:
    """Property test: current and longest streak never exceed active_dates + freezes_used count."""
    today = date(2026, 10, 17)
    # Test across multiple random-ish configurations
    for seed in range(50):
        active = {today - timedelta(days=i) for i in range(30) if (i * 7 + seed) % 3 == 0}
        freezes = {today - timedelta(days=i) for i in range(30) if (i * 5 + seed) % 7 == 0}
        summary = compute_streaks(
            active_dates=active,
            today=today,
            freezes_used=freezes,
            rules=StreakRules(),
        )
        total_eligible = len(active) + len(freezes)
        assert summary.current <= total_eligible
        assert summary.longest <= total_eligible
        assert summary.current <= summary.longest
