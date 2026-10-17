"""Content and curriculum knowledge endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, rate_limit
from app.content.service import GraphService
from app.db.models import Concept, ConceptEdge, Misconception, Problem, User
from app.errors import NotFoundError
from app.schemas.content import (
    ConceptDetailRead,
    ConceptRead,
    LearningPathResponse,
    MisconceptionRead,
    ProblemRead,
    TopicGraphResponse,
)

router = APIRouter(tags=["content"])


@router.get(
    "/concepts",
    response_model=list[ConceptRead],
    dependencies=[Depends(rate_limit())],
    summary="List active concepts",
    description="Retrieve active concepts with optional domain and topic filtering.",
)
async def list_concepts(
    domain: str | None = Query(None, description="Filter by domain"),
    topic: str | None = Query(None, description="Filter by topic"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ConceptRead]:
    """List active curriculum concepts."""
    query = select(Concept).where(Concept.is_active.is_(True))
    if domain:
        query = query.where(Concept.domain == domain)
    if topic:
        query = query.where(Concept.topic == topic)

    query = query.order_by(Concept.id.asc())
    result = await db.execute(query)
    concepts = result.scalars().all()
    return [ConceptRead.model_validate(c) for c in concepts]


@router.get(
    "/concepts/{concept_id}",
    response_model=ConceptDetailRead,
    dependencies=[Depends(rate_limit())],
    summary="Get concept details",
    description="Retrieve details, prerequisites, and misconceptions for a concept.",
)
async def get_concept(
    concept_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ConceptDetailRead:
    """Retrieve details for a single active concept."""
    stmt = select(Concept).where(
        Concept.id == concept_id,
        Concept.is_active.is_(True),
    )
    result = await db.execute(stmt)
    concept = result.scalar_one_or_none()
    if not concept:
        raise NotFoundError(f"Concept '{concept_id}' not found")

    # Fetch active direct prerequisites
    prereq_stmt = (
        select(ConceptEdge.source_id)
        .join(Concept, Concept.id == ConceptEdge.source_id)
        .where(
            ConceptEdge.target_id == concept_id,
            Concept.is_active.is_(True),
        )
        .order_by(ConceptEdge.source_id.asc())
    )
    prereq_res = await db.execute(prereq_stmt)
    prerequisites = list(prereq_res.scalars().all())

    # Fetch active misconceptions
    misc_stmt = (
        select(Misconception)
        .where(
            Misconception.concept_id == concept_id,
            Misconception.is_active.is_(True),
        )
        .order_by(Misconception.id.asc())
    )
    misc_res = await db.execute(misc_stmt)
    misconceptions = [MisconceptionRead.model_validate(m) for m in misc_res.scalars().all()]

    return ConceptDetailRead(
        id=concept.id,
        domain=concept.domain,
        topic=concept.topic,
        title=concept.title,
        description=concept.description,
        difficulty=concept.difficulty,
        prerequisites=prerequisites,
        misconceptions=misconceptions,
    )


@router.get(
    "/topics/{topic}/graph",
    response_model=TopicGraphResponse,
    dependencies=[Depends(rate_limit())],
    summary="Get topic prerequisite graph",
    description="Retrieve React Flow-friendly graph nodes and edges for a topic.",
)
async def get_topic_graph(
    topic: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TopicGraphResponse:
    """Retrieve prerequisite graph representation for a topic."""
    service = await GraphService.from_db(db, topic=topic)
    graph_data = service.get_topic_graph(topic)
    return TopicGraphResponse.model_validate(graph_data)


@router.get(
    "/concepts/{concept_id}/path",
    response_model=LearningPathResponse,
    dependencies=[Depends(rate_limit())],
    summary="Get concept learning path",
    description="Retrieve topologically ordered prerequisite path leading to target concept.",
)
async def get_concept_path(
    concept_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> LearningPathResponse:
    """Retrieve topological learning path for a concept."""
    concept_stmt = select(Concept.id).where(
        Concept.id == concept_id,
        Concept.is_active.is_(True),
    )
    res = await db.execute(concept_stmt)
    if not res.scalar_one_or_none():
        raise NotFoundError(f"Concept '{concept_id}' not found")

    service = await GraphService.from_db(db)
    path = service.learning_path(concept_id)
    return LearningPathResponse(concept_id=concept_id, path=path)


@router.get(
    "/problems",
    response_model=list[ProblemRead],
    dependencies=[Depends(rate_limit())],
    summary="List problems",
    description="Retrieve problems without answer specifications (learner-safe).",
)
async def list_problems(
    concept_id: str | None = Query(None, description="Filter problems by concept ID"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ProblemRead]:
    """Retrieve problems with answer_spec securely stripped."""
    query = select(Problem).where(Problem.is_active.is_(True))
    if concept_id:
        query = query.where(Problem.concept_id == concept_id)

    query = query.order_by(Problem.id.asc())
    result = await db.execute(query)
    problems = result.scalars().all()

    # Answer spec is omitted by schema definition (ProblemRead)
    return [ProblemRead.model_validate(p) for p in problems]
