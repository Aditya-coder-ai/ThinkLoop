"""Service layer for streak tracking, calendar heatmaps, and activity aggregates."""

import calendar
import uuid
from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.clock import Clock
from app.core.streak_calc import StreakRules, StreakSummary, compute_streaks
from app.db.models import ActivityEvent, DailyActivity, UserPreferences, UserStreakState
from app.schemas.streak import (
    CalendarDay,
    StreakResponse,
    StreakSeriesItem,
    StreakSeriesResponse,
)


class StreakService:
    """Business logic for streaks, calendar visualizations, and freeze operations."""

    def __init__(self, session: AsyncSession, settings: Settings, clock: Clock) -> None:
        self.session = session
        self.settings = settings
        self.clock = clock

    async def get_or_create_streak_state(self, user_id: uuid.UUID) -> UserStreakState:
        """Fetch or initialize the user's streak maintenance and freeze bank state."""
        stmt = select(UserStreakState).where(UserStreakState.user_id == user_id)
        result = await self.session.execute(stmt)
        state = result.scalar_one_or_none()

        if state is None:
            state = UserStreakState(
                user_id=user_id,
                freezes_available=self.settings.streak_initial_freezes,
                freezes_used_dates=[],
                longest_streak=0,
            )
            self.session.add(state)
            await self.session.flush()

        return state

    async def get_user_timezone(self, user_id: uuid.UUID) -> str:
        """Fetch learner timezone setting or default to UTC."""
        stmt = select(UserPreferences.timezone).where(UserPreferences.user_id == user_id)
        result = await self.session.execute(stmt)
        tz = result.scalar_one_or_none()
        return tz or "UTC"

    def evaluate_day_qualifying(
        self, events: list[ActivityEvent]
    ) -> tuple[bool, int, dict[str, int]]:
        """Evaluate if a set of daily activity events meets the qualifying threshold.

        Returns (is_qualifying, total_minutes, activity_counts).
        """
        counts: dict[str, int] = {}
        total_minutes = 0

        for ev in events:
            counts[ev.kind] = counts.get(ev.kind, 0) + 1
            meta = ev.meta or {}
            event_mins = int(meta.get("duration_minutes") or meta.get("minutes") or 0)
            if event_mins > 0:
                total_minutes += event_mins
            elif ev.kind == "focus_completed":
                total_minutes += self.settings.streak_min_focus_minutes
            elif ev.kind in (
                "tutor_turn_gradable",
                "review_completed",
                "battle_completed",
                "voice_session",
                "flashcard_reviewed",
                "doubt_resolved",
            ):
                total_minutes += 2

        # Qualifying rules
        tutor_qualifies = (
            counts.get("tutor_turn_gradable", 0) >= self.settings.streak_min_tutor_turns
        )
        focus_qualifies = (
            total_minutes >= self.settings.streak_min_focus_minutes and "focus_completed" in counts
        )
        other_qualifies = any(
            k in counts
            for k in (
                "review_completed",
                "battle_completed",
                "flashcard_reviewed",
                "doubt_resolved",
                "voice_session",
            )
        )
        is_qualifying = tutor_qualifies or focus_qualifies or other_qualifies

        return is_qualifying, total_minutes, counts

    def compute_intensity_level(
        self, minutes: int, is_qualifying: bool, freeze_applied: bool
    ) -> int:
        """Compute calendar heatmap intensity level from 0 to 4."""
        if freeze_applied:
            return 1
        if not is_qualifying and minutes == 0:
            return 0
        if minutes <= 15:
            return 1
        if minutes <= 30:
            return 2
        if minutes <= 60:
            return 3
        return 4

    async def get_streak_summary(self, user_id: uuid.UUID, today: date) -> StreakResponse:
        """Compute authoritative streak summary for the learner."""
        state = await self.get_or_create_streak_state(user_id)

        # 1. Fetch all materialized daily activity rows up to today
        daily_stmt = select(DailyActivity).where(
            and_(
                DailyActivity.user_id == user_id,
                DailyActivity.local_date <= today,
            )
        )
        daily_result = await self.session.execute(daily_stmt)
        daily_rows = daily_result.scalars().all()

        # 2. Query activity_events up to today to capture any un-materialized events
        events_stmt = select(ActivityEvent).where(
            and_(
                ActivityEvent.user_id == user_id,
                ActivityEvent.local_date <= today,
            )
        )
        events_result = await self.session.execute(events_stmt)
        events_by_date: dict[date, list[ActivityEvent]] = {}
        for ev in events_result.scalars().all():
            events_by_date.setdefault(ev.local_date, []).append(ev)

        # 3. Gather active dates from daily_rows and unrolled events
        active_dates = {row.local_date for row in daily_rows if row.is_qualifying}
        for d, ev_list in events_by_date.items():
            if d not in active_dates:
                is_q, _, _ = self.evaluate_day_qualifying(ev_list)
                if is_q:
                    active_dates.add(d)

        # 4. Gather freezes used
        freezes_used: set[date] = set()
        for iso_d in state.freezes_used_dates:
            try:
                freezes_used.add(date.fromisoformat(iso_d))
            except ValueError:
                continue

        for row in daily_rows:
            if row.freeze_applied:
                freezes_used.add(row.local_date)

        # 5. Compute pure streaks
        rules = StreakRules(
            freeze_earn_days=self.settings.streak_freeze_earn_days,
            freeze_max_cap=self.settings.streak_freeze_max_cap,
        )
        summary: StreakSummary = compute_streaks(
            active_dates=active_dates,
            today=today,
            freezes_used=freezes_used,
            rules=rules,
        )

        # Persist longest streak if improved
        if summary.longest > state.longest_streak:
            state.longest_streak = summary.longest
            await self.session.flush()

        return StreakResponse(
            current=summary.current,
            longest=max(summary.longest, state.longest_streak),
            at_risk=summary.at_risk,
            freezes_available=state.freezes_available,
            today_active=summary.today_active,
            last_active_date=summary.last_active_date,
        )

    async def get_calendar(
        self, user_id: uuid.UUID, year: int, month: int, today: date
    ) -> list[CalendarDay]:
        """Fetch heatmap activity calendar for the requested month."""
        state = await self.get_or_create_streak_state(user_id)
        _, days_in_month = calendar.monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)

        # Fetch daily activity in month range
        daily_stmt = select(DailyActivity).where(
            and_(
                DailyActivity.user_id == user_id,
                DailyActivity.local_date >= start_date,
                DailyActivity.local_date <= end_date,
            )
        )
        daily_result = await self.session.execute(daily_stmt)
        daily_map = {row.local_date: row for row in daily_result.scalars().all()}

        # Fetch unmaterialized events for days that are today or within this month
        events_stmt = select(ActivityEvent).where(
            and_(
                ActivityEvent.user_id == user_id,
                ActivityEvent.local_date >= start_date,
                ActivityEvent.local_date <= end_date,
            )
        )
        events_result = await self.session.execute(events_stmt)
        events_by_date: dict[date, list[ActivityEvent]] = {}
        for ev in events_result.scalars().all():
            events_by_date.setdefault(ev.local_date, []).append(ev)

        freezes_set = set()
        for iso_d in state.freezes_used_dates:
            try:
                freezes_set.add(date.fromisoformat(iso_d))
            except ValueError:
                continue

        calendar_days: list[CalendarDay] = []
        for day_num in range(1, days_in_month + 1):
            cur_date = date(year, month, day_num)
            if cur_date > today:
                calendar_days.append(
                    CalendarDay(
                        date=cur_date,
                        minutes=0,
                        activity_counts={},
                        level=0,
                        freeze_used=False,
                        is_qualifying=False,
                    )
                )
                continue

            row = daily_map.get(cur_date)
            unrolled = events_by_date.get(cur_date, [])

            if row is not None:
                minutes = row.minutes
                counts = row.counts
                is_qualifying = row.is_qualifying
                freeze_applied = row.freeze_applied or (cur_date in freezes_set)

                # If there are additional unrolled events (e.g. today)
                if unrolled:
                    ev_qualifying, ev_mins, ev_counts = self.evaluate_day_qualifying(unrolled)
                    if ev_mins > minutes:
                        minutes = ev_mins
                    if ev_qualifying:
                        is_qualifying = True
                    for k, v in ev_counts.items():
                        counts[k] = max(counts.get(k, 0), v)
            elif unrolled:
                is_qualifying, minutes, counts = self.evaluate_day_qualifying(unrolled)
                freeze_applied = cur_date in freezes_set
            else:
                minutes = 0
                counts = {}
                is_qualifying = False
                freeze_applied = cur_date in freezes_set

            level = self.compute_intensity_level(minutes, is_qualifying, freeze_applied)
            calendar_days.append(
                CalendarDay(
                    date=cur_date,
                    minutes=minutes,
                    activity_counts=counts,
                    level=level,
                    freeze_used=freeze_applied,
                    is_qualifying=is_qualifying,
                )
            )

        return calendar_days

    async def get_summary_series(
        self, user_id: uuid.UUID, days: int, today: date
    ) -> StreakSeriesResponse:
        """Fetch aggregated chronological series of study activity for charts."""
        streak_resp = await self.get_streak_summary(user_id, today)

        start_date = today - timedelta(days=days - 1)
        daily_stmt = select(DailyActivity).where(
            and_(
                DailyActivity.user_id == user_id,
                DailyActivity.local_date >= start_date,
                DailyActivity.local_date <= today,
            )
        )
        daily_result = await self.session.execute(daily_stmt)
        daily_map = {row.local_date: row for row in daily_result.scalars().all()}

        # Query unrolled events in date range
        events_stmt = select(ActivityEvent).where(
            and_(
                ActivityEvent.user_id == user_id,
                ActivityEvent.local_date >= start_date,
                ActivityEvent.local_date <= today,
            )
        )
        events_result = await self.session.execute(events_stmt)
        events_by_date: dict[date, list[ActivityEvent]] = {}
        for ev in events_result.scalars().all():
            events_by_date.setdefault(ev.local_date, []).append(ev)

        series: list[StreakSeriesItem] = []
        total_active_days = 0
        total_minutes = 0

        for i in range(days):
            cur_date = start_date + timedelta(days=i)
            row = daily_map.get(cur_date)
            unrolled = events_by_date.get(cur_date, [])

            if row is not None:
                is_active = row.is_qualifying
                minutes = row.minutes
                act_count = sum(row.counts.values())
                freeze_used = row.freeze_applied

                if unrolled:
                    ev_qualifying, ev_mins, ev_counts = self.evaluate_day_qualifying(unrolled)
                    if ev_qualifying:
                        is_active = True
                    minutes = max(minutes, ev_mins)
                    act_count = max(act_count, sum(ev_counts.values()))
            elif unrolled:
                ev_qualifying, ev_mins, ev_counts = self.evaluate_day_qualifying(unrolled)
                is_active = ev_qualifying
                minutes = ev_mins
                act_count = sum(ev_counts.values())
                freeze_used = False
            else:
                is_active = False
                minutes = 0
                act_count = 0
                freeze_used = False

            if is_active:
                total_active_days += 1
            total_minutes += minutes

            series.append(
                StreakSeriesItem(
                    date=cur_date,
                    minutes=minutes,
                    activity_count=act_count,
                    is_active=is_active,
                    freeze_used=freeze_used,
                )
            )

        return StreakSeriesResponse(
            days=days,
            total_active_days=total_active_days,
            total_minutes=total_minutes,
            current_streak=streak_resp.current,
            longest_streak=streak_resp.longest,
            series=series,
        )
