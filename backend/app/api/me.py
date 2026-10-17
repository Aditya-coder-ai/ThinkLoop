from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, rate_limit
from app.db.models import User
from app.schemas.mastery import ProgressSummary
from app.schemas.user import UserRead
from app.services.mastery import MasteryService

router = APIRouter(tags=["user"])


@router.get(
    "/me",
    response_model=UserRead,
    dependencies=[Depends(rate_limit())],
    summary="Get current user profile",
    description=(
        "Returns profile information for the authenticated user, provisioning if first visit."
    ),
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    """Return profile of the authenticated user."""
    return UserRead.model_validate(current_user)


@router.get(
    "/me/progress",
    response_model=ProgressSummary,
    dependencies=[Depends(rate_limit())],
    summary="Get current user progress",
    description="Returns cumulative concept mastery counts and misconception resolution stats.",
)
async def get_my_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProgressSummary:
    """Return user progress summary across concepts and misconceptions."""
    mastery_service = MasteryService()
    return await mastery_service.get_user_progress(db=db, user_id=current_user.id)
