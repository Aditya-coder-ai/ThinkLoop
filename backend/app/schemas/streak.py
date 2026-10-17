import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class StreakResponse(BaseModel):
    """Current streak status and freeze availability for the learner."""

    model_config = ConfigDict(extra="forbid")

    current: int = Field(ge=0, description="Current streak count in days")
    longest: int = Field(ge=0, description="Longest historical streak count in days")
    at_risk: bool = Field(description="True if streak will break if no activity completed today")
    freezes_available: int = Field(ge=0, description="Number of banked streak freezes available")
    today_active: bool = Field(description="True if qualifying activity completed today")
    last_active_date: dt.date | None = Field(
        default=None, description="Most recent date with qualifying activity"
    )


class CalendarDay(BaseModel):
    """Calendar heatmap data for a single day."""

    model_config = ConfigDict(extra="forbid")

    date: dt.date = Field(description="Calendar date")
    minutes: int = Field(ge=0, description="Active study minutes logged on this day")
    activity_counts: dict[str, int] = Field(
        default_factory=dict, description="Count of activities logged by kind"
    )
    level: int = Field(ge=0, le=4, description="Heatmap intensity level from 0 (none) to 4 (high)")
    freeze_used: bool = Field(description="True if a streak freeze covered this day")
    is_qualifying: bool = Field(
        description="True if this day met the qualifying activity threshold"
    )


class StreakSeriesItem(BaseModel):
    """Aggregated daily item for historical charts."""

    model_config = ConfigDict(extra="forbid")

    date: dt.date
    minutes: int
    activity_count: int
    is_active: bool
    freeze_used: bool


class StreakSeriesResponse(BaseModel):
    """Aggregated series response for charting learner consistency."""

    model_config = ConfigDict(extra="forbid")

    days: int
    total_active_days: int
    total_minutes: int
    current_streak: int
    longest_streak: int
    series: list[StreakSeriesItem]
