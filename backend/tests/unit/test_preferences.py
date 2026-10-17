"""Unit tests for user preferences validation."""

import pytest
from pydantic import ValidationError

from app.schemas.preferences import UserPreferencesUpdate, validate_iana_timezone


@pytest.mark.parametrize(
    "tz_name",
    [
        "UTC",
        "America/New_York",
        "Asia/Kolkata",
        "Europe/London",
        "Asia/Tokyo",
        "Australia/Sydney",
        "Pacific/Auckland",
    ],
)
def test_valid_iana_timezones(tz_name: str) -> None:
    assert validate_iana_timezone(tz_name) == tz_name
    update = UserPreferencesUpdate(timezone=tz_name)
    assert update.timezone == tz_name


@pytest.mark.parametrize(
    "bad_tz",
    [
        "Not/A_Real_Timezone",
        "Mars/Olympus_Mons",
        "InvalidZone",
        "UTC+5",
        "US/Eastern_Fake",
        "",
    ],
)
def test_invalid_iana_timezones_raise_error(bad_tz: str) -> None:
    with pytest.raises(ValueError):
        validate_iana_timezone(bad_tz)

    with pytest.raises(ValidationError):
        UserPreferencesUpdate(timezone=bad_tz)


def test_daily_goal_minutes_validation() -> None:
    valid = UserPreferencesUpdate(daily_goal_minutes=45)
    assert valid.daily_goal_minutes == 45

    with pytest.raises(ValidationError):
        UserPreferencesUpdate(daily_goal_minutes=0)

    with pytest.raises(ValidationError):
        UserPreferencesUpdate(daily_goal_minutes=2000)
