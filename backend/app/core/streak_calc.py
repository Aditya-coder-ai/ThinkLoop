"""Pure streak calculation engine for Thinkloop (Phase 10).

Adheres strictly to the Thinkloop principle: streaks and calendars are
server-authoritative, deterministic pure functions evaluated on local dates.
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class StreakRules:
    """Configurable rules governing streak maintenance and freeze accrual."""

    freeze_earn_days: int = 7
    freeze_max_cap: int = 2


@dataclass(frozen=True)
class StreakSummary:
    """Summary of current and historical streak state."""

    current: int
    longest: int
    last_active_date: date | None
    at_risk: bool
    today_active: bool


def compute_streaks(
    active_dates: set[date],
    today: date,
    freezes_used: set[date] | None = None,
    rules: StreakRules | None = None,
) -> StreakSummary:
    """Pure deterministic calculation of learner streak and heatmap metrics.

    Args:
        active_dates: Set of dates where the user had at least one qualifying activity.
        today: Authoritative current date in the user's local timezone.
        freezes_used: Set of dates where a streak freeze was legally applied.
        rules: Streak calculation and freeze accrual parameters.

    Returns:
        StreakSummary with current, longest, last_active_date, at_risk, and today_active.
    """
    if rules is None:
        rules = StreakRules()

    # Filter out future dates for safety
    valid_active = {d for d in active_dates if d <= today}
    valid_freezes = {d for d in (freezes_used or set()) if d < today}

    today_active = today in valid_active
    last_active_date = max(valid_active, default=None)

    if not valid_active:
        return StreakSummary(
            current=0,
            longest=0,
            last_active_date=None,
            at_risk=False,
            today_active=False,
        )

    # Walk from earliest active date to today
    min_date = min(valid_active)
    total_days = (today - min_date).days + 1

    current_run = 0
    longest_run = 0
    consecutive_freezes = 0
    has_active_in_run = False
    run_at_yesterday = 0

    yesterday = today - timedelta(days=1)

    for i in range(total_days):
        d = min_date + timedelta(days=i)

        if d in valid_active:
            current_run += 1
            consecutive_freezes = 0
            has_active_in_run = True
            if current_run > longest_run:
                longest_run = current_run
        elif d in valid_freezes and has_active_in_run and consecutive_freezes == 0:
            current_run += 1
            consecutive_freezes = 1
            if current_run > longest_run:
                longest_run = current_run
        else:
            current_run = 0
            consecutive_freezes = 0
            has_active_in_run = False

        if d == yesterday:
            run_at_yesterday = current_run

    if today_active:
        current = current_run
        at_risk = False
    elif run_at_yesterday > 0:
        current = run_at_yesterday
        at_risk = True
    else:
        current = 0
        at_risk = False

    return StreakSummary(
        current=current,
        longest=longest_run,
        last_active_date=last_active_date,
        at_risk=at_risk,
        today_active=today_active,
    )
