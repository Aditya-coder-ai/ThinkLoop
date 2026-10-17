"""API router for streak calendar, heatmaps, and streak status (Phase 10)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_clock,
    get_current_user,
    get_db,
    rate_limit,
    require_feature,
)
from app.config import Settings, get_settings
from app.core.activity import compute_local_date
from app.core.clock import Clock
from app.db.models import User
from app.schemas.streak import CalendarDay, StreakResponse, StreakSeriesResponse
from app.services.streak import StreakService

router = APIRouter(
    prefix="/streak",
    tags=["streak"],
    dependencies=[
        Depends(require_feature("feature_streak")),
        Depends(rate_limit()),
    ],
)


@router.get("", response_model=StreakResponse)
async def get_streak(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreakResponse:
    """Get the current and longest streak, freeze status, and today's activity state."""
    service = StreakService(session=session, settings=settings, clock=clock)
    tz = await service.get_user_timezone(user.id)
    today = compute_local_date(clock.now(), tz)
    return await service.get_streak_summary(user.id, today)


@router.get("/calendar", response_model=list[CalendarDay])
async def get_calendar(
    month: Annotated[
        str,
        Query(
            pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
            description="Target calendar month in YYYY-MM format",
        ),
    ],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[CalendarDay]:
    """Get the daily activity heatmap for a given month."""
    parts = month.split("-")
    year, month_num = int(parts[0]), int(parts[1])

    service = StreakService(session=session, settings=settings, clock=clock)
    tz = await service.get_user_timezone(user.id)
    today = compute_local_date(clock.now(), tz)
    return await service.get_calendar(user.id, year, month_num, today)


@router.get("/summary", response_model=StreakSeriesResponse)
async def get_summary(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
    days: Annotated[
        int,
        Query(
            ge=1,
            le=365,
            description="Number of days to include in the aggregated series",
        ),
    ] = 90,
) -> StreakSeriesResponse:
    """Get aggregated activity series for charting consistency."""
    service = StreakService(session=session, settings=settings, clock=clock)
    tz = await service.get_user_timezone(user.id)
    today = compute_local_date(clock.now(), tz)
    return await service.get_summary_series(user.id, days, today)
