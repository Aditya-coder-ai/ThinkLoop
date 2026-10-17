"""User preferences API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, rate_limit
from app.db.models import User, UserPreferences
from app.schemas.preferences import UserPreferencesRead, UserPreferencesUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/me/preferences", tags=["Preferences"])


@router.get(
    "",
    response_model=UserPreferencesRead,
    dependencies=[Depends(rate_limit())],
    summary="Get current user preferences",
)
async def get_preferences(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPreferences:
    """Retrieve the authenticated user's preferences, initializing defaults if absent."""
    query = select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    result = await db.execute(query)
    preferences = result.scalar_one_or_none()

    if preferences is None:
        preferences = UserPreferences(
            user_id=current_user.id,
            timezone="UTC",
            daily_goal_minutes=20,
            voice_enabled=False,
            preferred_voice="alloy",
            locale="en-US",
        )
        db.add(preferences)
        await db.commit()
        await db.refresh(preferences)

    return preferences


@router.put(
    "",
    response_model=UserPreferencesRead,
    dependencies=[Depends(rate_limit())],
    summary="Update current user preferences",
)
async def update_preferences(
    update_data: UserPreferencesUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPreferences:
    """Update user preferences with validated timezone and settings."""
    query = select(UserPreferences).where(UserPreferences.user_id == current_user.id)
    result = await db.execute(query)
    preferences = result.scalar_one_or_none()

    if preferences is None:
        preferences = UserPreferences(
            user_id=current_user.id,
            timezone=update_data.timezone or "UTC",
            daily_goal_minutes=update_data.daily_goal_minutes
            if update_data.daily_goal_minutes is not None
            else 20,
            voice_enabled=update_data.voice_enabled
            if update_data.voice_enabled is not None
            else False,
            preferred_voice=update_data.preferred_voice or "alloy",
            locale=update_data.locale or "en-US",
        )
        db.add(preferences)
    else:
        if update_data.timezone is not None:
            preferences.timezone = update_data.timezone
        if update_data.daily_goal_minutes is not None:
            preferences.daily_goal_minutes = update_data.daily_goal_minutes
        if update_data.voice_enabled is not None:
            preferences.voice_enabled = update_data.voice_enabled
        if update_data.preferred_voice is not None:
            preferences.preferred_voice = update_data.preferred_voice
        if update_data.locale is not None:
            preferences.locale = update_data.locale

    await db.commit()
    await db.refresh(preferences)
    return preferences
