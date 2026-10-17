"""Current authenticated user, learner profile, progress, and mastery endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, rate_limit
from app.db.models import User
from app.db.repository import (
    get_concept_by_id,
    get_learner_mastery,
    get_learner_profile,
    upsert_learner_mastery,
    upsert_learner_profile,
)
from app.errors import NotFoundError
from app.schemas.learner import (
    LearnerMasteryRead,
    LearnerMasteryUpsert,
    ProfileRead,
    ProfileUpdate,
)
from app.schemas.mastery import ProgressSummary
from app.schemas.user import UserRead
from app.services.mastery import MasteryService

router = APIRouter(tags=["user"])


@router.get(
    "/me",
    response_model=UserRead,
    dependencies=[Depends(rate_limit())],
    summary="Get current user account",
    description="Returns account identity for the authenticated user.",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    """Return account identity of the authenticated user."""
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


@router.get(
    "/me/profile",
    response_model=ProfileRead,
    dependencies=[Depends(rate_limit())],
    summary="Get learner profile",
    description="Returns the learning profile for the authenticated user, or 404 if not set.",
)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProfileRead:
    """Return learner profile for authenticated user with strict identity scoping."""
    profile = await get_learner_profile(session, user_id=current_user.auth_id)
    if not profile:
        raise NotFoundError("Learner profile not found for authenticated user")
    return ProfileRead.model_validate(profile)


@router.put(
    "/me/profile",
    response_model=ProfileRead,
    dependencies=[Depends(rate_limit())],
    summary="Create or update learner profile",
    description="Safely upserts learner profile fields for the authenticated user.",
)
async def update_my_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ProfileRead:
    """Upsert learner profile using verified authentication identity."""
    profile = await upsert_learner_profile(
        session,
        user_id=current_user.auth_id,
        display_name=payload.display_name,
        learning_level=payload.learning_level,
        exam_target=payload.exam_target,
    )
    return ProfileRead.model_validate(profile)


@router.get(
    "/me/mastery",
    response_model=list[LearnerMasteryRead],
    dependencies=[Depends(rate_limit())],
    summary="Get learner mastery records",
    description="Returns mastery progress records for the authenticated user.",
)
async def get_my_mastery(
    concept_id: str | None = Query(None, description="Optional filter by concept ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[LearnerMasteryRead]:
    """Retrieve verified user's concept mastery progress."""
    records = await get_learner_mastery(
        session,
        user_id=current_user.auth_id,
        concept_id=concept_id,
    )
    return [LearnerMasteryRead.model_validate(r) for r in records]


@router.post(
    "/me/mastery",
    response_model=LearnerMasteryRead,
    dependencies=[Depends(rate_limit())],
    summary="Record or update concept mastery",
    description="Upserts concept mastery progress without creating duplicate records.",
)
async def update_my_mastery(
    payload: LearnerMasteryUpsert,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> LearnerMasteryRead:
    """Upsert mastery score and attempts with verified user ownership."""
    # Ensure learner profile exists before attaching mastery
    profile = await get_learner_profile(session, user_id=current_user.auth_id)
    if not profile:
        # Auto-provision profile with default attributes
        await upsert_learner_profile(session, user_id=current_user.auth_id)

    # Validate concept exists if active in concepts table
    concept = await get_concept_by_id(session, concept_id=payload.concept_id)
    if not concept:
        raise NotFoundError(f"Concept '{payload.concept_id}' does not exist")

    mastery = await upsert_learner_mastery(
        session,
        user_id=current_user.auth_id,
        concept_id=payload.concept_id,
        mastery_score=payload.mastery_score,
        attempts_increment=payload.attempts_increment,
        last_practiced_at=payload.last_practiced_at,
        next_review_at=payload.next_review_at,
    )
    return LearnerMasteryRead.model_validate(mastery)
