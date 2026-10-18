"""Dialogue Sessions and SSE Chat Streaming API Endpoints."""

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

if TYPE_CHECKING:
    RedisClient = Redis[str]
else:
    RedisClient = Redis

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.api.deps import (
    get_current_user,
    get_db,
    get_orchestrator,
    get_redis,
    rate_limit,
)
from app.core.orchestrator import Orchestrator
from app.db.models import Concept, Session, User
from app.errors import ConflictError, NotFoundError
from app.schemas.chat import MessageRequest, SessionCreate, SessionRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post(
    "",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit())],
)
async def create_session(
    body: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionRead:
    """Create a new dialogue session on a concept for the authenticated user."""
    concept_stmt = select(Concept).where(
        Concept.id == body.concept_id,
        Concept.is_active.is_(True),
    )
    concept = (await db.execute(concept_stmt)).scalar_one_or_none()
    if not concept:
        raise NotFoundError(
            message=f"Concept '{body.concept_id}' not found",
            code="NOT_FOUND",
        )

    session = Session(
        id=uuid.uuid4(),
        user_id=current_user.id,
        concept_id=concept.id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return SessionRead(
        id=session.id,
        user_id=session.user_id,
        concept_id=session.concept_id,
        summary=session.summary,
        started_at=session.started_at,
        ended_at=session.ended_at,
        turns=[],
    )


@router.get(
    "/{session_id}",
    response_model=SessionRead,
    dependencies=[Depends(rate_limit())],
)
async def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionRead:
    """Retrieve dialogue session and turn history.

    Returns 404 if session does not exist or belongs to another user.
    """
    stmt = select(Session).options(selectinload(Session.turns)).where(Session.id == session_id)
    session = (await db.execute(stmt)).scalar_one_or_none()

    if not session or session.user_id != current_user.id:
        raise NotFoundError(
            message=f"Session '{session_id}' not found",
            code="NOT_FOUND",
        )

    return SessionRead.model_validate(session)


@router.post(
    "/{session_id}/messages",
    dependencies=[Depends(rate_limit())],
)
async def post_message(
    session_id: uuid.UUID,
    body: MessageRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    orchestrator: Orchestrator | None = Depends(get_orchestrator),
    llm: Any = None,
    diagnoser: Any = None,
) -> StreamingResponse:
    """Submit learner message and stream pedagogical tutor reply via Server-Sent Events (SSE)."""
    if llm is not None or orchestrator is None:
        from app.config import get_settings
        from app.services.history import HistoryService
        from app.services.llm import FakeLLMClient
        from app.services.mastery import MasteryService

        app_settings = getattr(request.app.state, "settings", None) or get_settings()
        effective_llm = llm or FakeLLMClient()
        effective_diagnoser = diagnoser
        if effective_diagnoser is None:
            from app.api.deps import get_diagnoser_service

            effective_diagnoser = await get_diagnoser_service(
                llm=effective_llm, db=db, settings=app_settings
            )
        orchestrator = Orchestrator(
            llm_client=effective_llm,
            diagnoser=effective_diagnoser,
            mastery_service=MasteryService(),
            history_service=HistoryService(),
            settings=app_settings,
        )
    # 1. Validate session exists and belongs to current user
    stmt = select(Session).where(Session.id == session_id)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session or session.user_id != current_user.id:
        raise NotFoundError(
            message=f"Session '{session_id}' not found",
            code="NOT_FOUND",
        )

    # 2. Acquire Redis distributed lock (enforce single in-flight turn per session)
    lock_key = f"chat:lock:{session_id}"
    lock_acquired = False
    try:
        acquired = await redis.set(lock_key, "1", nx=True, ex=60)
        if not acquired:
            raise ConflictError(
                message="A message turn is already in-flight for this session",
                code="CONFLICT",
            )
        lock_acquired = True
    except ConflictError:
        raise
    except Exception as exc:
        logger.warning(
            "Redis unavailable during chat turn lock acquisition for session_id=%s: %s. Failing open.",
            session_id,
            exc,
        )

    # 3. Log metadata without raw learner message content
    logger.info(
        "Initiating chat turn for session_id=%s, user_id=%s, message_len=%d",
        session_id,
        current_user.id,
        len(body.content),
    )

    # 4. Fetch concept details
    concept_stmt = select(Concept).where(Concept.id == session.concept_id)
    concept = (await db.execute(concept_stmt)).scalar_one_or_none()
    if not concept:
        if lock_acquired:
            try:
                await redis.delete(lock_key)
            except Exception:
                pass
        raise NotFoundError(
            message=f"Concept '{session.concept_id}' not found",
            code="NOT_FOUND",
        )

    session_factory: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "session_factory", None
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        turn_gen = orchestrator.run_turn(
            session=session,
            concept=concept,
            learner_message=body.content,
            user_id=current_user.id,
            db=db,
            session_factory=session_factory,
        )
        try:
            async for event in turn_gen:
                yield event.to_sse()
        except (asyncio.CancelledError, GeneratorExit):
            await turn_gen.aclose()
            raise
        finally:
            if lock_acquired:
                try:
                    await redis.delete(lock_key)
                    logger.info("Released turn lock for session_id=%s", session.id)
                except Exception as exc:
                    logger.warning("Failed to release Redis turn lock: %s", exc)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
