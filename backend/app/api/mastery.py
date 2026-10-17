"""Mastery topic knowledge graph endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, rate_limit
from app.db.models import User
from app.schemas.mastery import TopicMasteryResponse
from app.services.mastery import MasteryService

router = APIRouter(prefix="/mastery", tags=["mastery"])


@router.get(
    "",
    response_model=TopicMasteryResponse,
    dependencies=[Depends(rate_limit())],
    summary="Get user topic concept mastery graph",
)
async def get_topic_mastery(
    topic: str = Query(..., description="Topic identifier, e.g. mechanics"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TopicMasteryResponse:
    """Return knowledge graph nodes decorated with learner mastery and prerequisite edges."""
    mastery_service = MasteryService()
    return await mastery_service.get_topic_mastery(
        db=db,
        user_id=current_user.id,
        topic=topic,
    )
