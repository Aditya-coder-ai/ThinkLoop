"""Unit tests for typed database repository operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Concept, Profile
from app.db.repository import (
    check_db_connectivity,
    get_concept_by_id,
    get_learner_mastery,
    get_learner_profile,
    list_concepts,
    upsert_learner_mastery,
    upsert_learner_profile,
)


@pytest.fixture
async def db_session():
    """In-memory SQLite session with schema initialized for repository tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_check_db_connectivity(db_session: AsyncSession) -> None:
    """check_db_connectivity returns True on operational database."""
    connected = await check_db_connectivity(db_session)
    assert connected is True


@pytest.mark.asyncio
async def test_concepts_listing_and_filtering(db_session: AsyncSession) -> None:
    """list_concepts accurately filters by domain, topic, and subject."""
    c1 = Concept(
        id="physics_vectors",
        domain="physics",
        subject="physics",
        topic="mechanics",
        title="Vectors and Scalars",
        description="Detailed description of vector fundamentals and properties.",
        difficulty=2,
        content_hash="hash1",
        is_active=True,
    )
    c2 = Concept(
        id="physics_kinematics",
        domain="physics",
        subject="physics",
        topic="kinematics",
        title="1D Kinematics",
        description="Detailed description of 1D kinematics formulas and motion.",
        difficulty=3,
        content_hash="hash2",
        is_active=True,
    )
    c3 = Concept(
        id="math_quadratics",
        domain="math",
        subject="mathematics",
        topic="algebra",
        title="Quadratic Equations",
        description="Detailed description of quadratic equation factoring and roots.",
        difficulty=2,
        content_hash="hash3",
        is_active=True,
    )
    c_inactive = Concept(
        id="inactive_concept",
        domain="physics",
        subject="physics",
        topic="mechanics",
        title="Archived Concept",
        description="Detailed description of an inactive curriculum concept.",
        difficulty=1,
        content_hash="hash4",
        is_active=False,
    )
    db_session.add_all([c1, c2, c3, c_inactive])
    await db_session.commit()

    # All active concepts
    all_concepts = await list_concepts(db_session)
    assert len(all_concepts) == 3
    ids = [c.id for c in all_concepts]
    assert "inactive_concept" not in ids

    # Filter by domain
    physics_concepts = await list_concepts(db_session, domain="physics")
    assert len(physics_concepts) == 2

    # Filter by topic
    mechanics_concepts = await list_concepts(db_session, topic="mechanics")
    assert len(mechanics_concepts) == 1
    assert mechanics_concepts[0].id == "physics_vectors"

    # Filter by subject
    math_concepts = await list_concepts(db_session, subject="mathematics")
    assert len(math_concepts) == 1
    assert math_concepts[0].id == "math_quadratics"


@pytest.mark.asyncio
async def test_get_concept_by_id(db_session: AsyncSession) -> None:
    """get_concept_by_id returns concept if active, None if non-existent or inactive."""
    c = Concept(
        id="sample_concept",
        domain="physics",
        subject="physics",
        topic="energy",
        title="Conservation of Energy",
        description="Detailed description of conservation of mechanical energy.",
        difficulty=3,
        content_hash="hash_e",
        is_active=True,
    )
    db_session.add(c)
    await db_session.commit()

    found = await get_concept_by_id(db_session, "sample_concept")
    assert found is not None
    assert found.title == "Conservation of Energy"

    missing = await get_concept_by_id(db_session, "non_existent_concept")
    assert missing is None


@pytest.mark.asyncio
async def test_profile_creation_and_retrieval(db_session: AsyncSession) -> None:
    """upsert_learner_profile creates profile and allows safe retrieval."""
    user_id = "auth0|user_test_1"

    # Initially missing
    initial = await get_learner_profile(db_session, user_id=user_id)
    assert initial is None

    # Create profile
    created = await upsert_learner_profile(
        db_session,
        user_id=user_id,
        display_name="Alex Learner",
        learning_level="College students",
        exam_target="JEE Advanced",
    )
    assert created.user_id == user_id
    assert created.display_name == "Alex Learner"
    assert created.learning_level == "College students"
    assert created.exam_target == "JEE Advanced"

    # Retrieve profile
    fetched = await get_learner_profile(db_session, user_id=user_id)
    assert fetched is not None
    assert fetched.display_name == "Alex Learner"

    # Update profile safely
    updated = await upsert_learner_profile(
        db_session,
        user_id=user_id,
        display_name="Alex Master",
        learning_level="Advanced",
    )
    assert updated.display_name == "Alex Master"
    assert updated.learning_level == "Advanced"
    # exam_target should be preserved
    assert updated.exam_target == "JEE Advanced"


@pytest.mark.asyncio
async def test_mastery_upsert_prevents_duplicate_records(db_session: AsyncSession) -> None:
    """Upsert learner mastery updates progress without duplicate records for concept."""
    user_id = "auth0|user_test_mastery"
    concept_id = "concept_physics_momentum"

    # Seed profile and concept
    profile = Profile(user_id=user_id, display_name="Study Partner")
    concept = Concept(
        id=concept_id,
        domain="physics",
        topic="momentum",
        title="Conservation of Momentum",
        description="Detailed description of linear momentum and impulse.",
        difficulty=3,
        content_hash="hash_m",
        is_active=True,
    )
    db_session.add_all([profile, concept])
    await db_session.commit()

    # First attempt: mastery_score 0.4
    m1 = await upsert_learner_mastery(
        db_session,
        user_id=user_id,
        concept_id=concept_id,
        mastery_score=0.4,
        attempts_increment=1,
    )
    assert m1.mastery_score == 0.4
    assert m1.attempts == 1

    # Second attempt: mastery_score 0.85
    m2 = await upsert_learner_mastery(
        db_session,
        user_id=user_id,
        concept_id=concept_id,
        mastery_score=0.85,
        attempts_increment=1,
    )
    assert m2.mastery_score == 0.85
    assert m2.attempts == 2

    # Verify only 1 record exists in database for this user and concept
    records = await get_learner_mastery(db_session, user_id=user_id)
    assert len(records) == 1
    assert records[0].attempts == 2
    assert records[0].mastery_score == 0.85


@pytest.mark.asyncio
async def test_user_isolation(db_session: AsyncSession) -> None:
    """Queries and mutations strictly isolate records between distinct users."""
    user_a = "auth0|user_A"
    user_b = "auth0|user_B"
    concept_id = "concept_common"

    concept = Concept(
        id=concept_id,
        domain="physics",
        topic="mechanics",
        title="Common Concept",
        description="Detailed description of common physics concept for isolation tests.",
        difficulty=1,
        content_hash="hash_iso",
        is_active=True,
    )
    db_session.add(concept)
    await db_session.commit()

    # User A profile and mastery
    await upsert_learner_profile(db_session, user_id=user_a, display_name="User Alpha")
    await upsert_learner_mastery(
        db_session, user_id=user_a, concept_id=concept_id, mastery_score=0.9
    )

    # User B profile and mastery
    await upsert_learner_profile(db_session, user_id=user_b, display_name="User Beta")
    await upsert_learner_mastery(
        db_session, user_id=user_b, concept_id=concept_id, mastery_score=0.3
    )

    # Verify User A only sees User A records
    profile_a = await get_learner_profile(db_session, user_id=user_a)
    assert profile_a is not None
    assert profile_a.display_name == "User Alpha"

    mastery_a = await get_learner_mastery(db_session, user_id=user_a)
    assert len(mastery_a) == 1
    assert mastery_a[0].mastery_score == 0.9

    # Verify User B only sees User B records
    profile_b = await get_learner_profile(db_session, user_id=user_b)
    assert profile_b is not None
    assert profile_b.display_name == "User Beta"

    mastery_b = await get_learner_mastery(db_session, user_id=user_b)
    assert len(mastery_b) == 1
    assert mastery_b[0].mastery_score == 0.3
