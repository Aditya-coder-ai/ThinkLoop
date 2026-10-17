"""Integration tests for the dialogue Turn Orchestrator (Phase 6)."""

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.core.diagnoser import DiagnoserService
from app.core.orchestrator import Orchestrator, OrchestratorEvent
from app.core.strategy import StrategyType
from app.db.base import Base
from app.db.models import (
    ActivityEvent,
    Concept,
    ConceptEdge,
    Mastery,
    Misconception,
    Problem,
    Session,
    Turn,
    User,
)
from app.services.history import HistoryService
from app.services.llm import FakeLLMClient, LLMResult, LLMTimeoutError
from app.services.mastery import MasteryService


@pytest.fixture
async def orchestrator_fixture(tmp_path: Any):
    """Set up isolated SQLite test database and Orchestrator components."""
    db_file = tmp_path / "orchestrator_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    test_user_id = uuid.uuid4()
    # Seed user, concepts, edges, misconceptions, and problems
    async with session_factory() as db:
        user = User(id=test_user_id, auth_id="auth_orchestrator_user", email="orch@example.com")
        db.add(user)

        prereq = Concept(
            id="c_prereq",
            domain="physics",
            topic="mechanics",
            title="Coordinate Systems",
            description="Foundational understanding of 1D and 2D Cartesian coordinate frames.",
            difficulty=1,
            schema_version=1,
            is_active=True,
            content_hash="h_prereq",
            embedding=[0.01] * 1024,
        )
        db.add(prereq)

        concept = Concept(
            id="c_target",
            domain="physics",
            topic="mechanics",
            title="Newton's Second Law",
            description=(
                "The net external force on a body is directly proportional to its "
                "acceleration: F = m*a."
            ),
            difficulty=2,
            schema_version=1,
            is_active=True,
            content_hash="h_target",
            embedding=[0.01] * 1024,
        )
        db.add(concept)

        edge = ConceptEdge(source_id="c_prereq", target_id="c_target")
        db.add(edge)

        misc = Misconception(
            id="m_force_motion",
            concept_id="c_target",
            statement="A net force is required to sustain continuous constant velocity motion.",
            correct_idea="Zero net force means constant velocity (acceleration is zero).",
            conflict_prompt=(
                "Consider a voyager probe drifting in deep interstellar space "
                "with engines shut down."
            ),
            example_utterances=[
                "You need to keep pushing or it stops",
                "Constant speed needs a constant push",
                "Force keeps objects moving at constant speed",
            ],
            evidence="Hestenes et al., 1992",
            schema_version=1,
            is_active=True,
            content_hash="hm_orch",
            embedding=[0.01] * 1024,
        )
        db.add(misc)

        problem = Problem(
            id="p_accel_1",
            concept_id="c_target",
            statement=(
                "A 5 kg sled experiences a net horizontal force of 20 N. What is its acceleration?"
            ),
            difficulty=1,
            answer_spec={"type": "numeric", "value": 4.0, "unit": "m/s^2", "tolerance": 0.01},
            schema_version=1,
            is_active=True,
            content_hash="hp_orch",
        )
        db.add(problem)

        session = Session(
            id=uuid.uuid4(),
            user_id=test_user_id,
            concept_id="c_target",
        )
        db.add(session)

        await db.commit()

    fake_llm = FakeLLMClient()
    settings = Settings(
        DATABASE_URL=db_url,
        REDIS_URL="redis://localhost:6379/0",
        AUTH_JWKS_URL="https://auth.thinkloop.ai/.well-known/jwks.json",
        AUTH_ISSUER="https://auth.thinkloop.ai",
        AUTH_AUDIENCE="thinkloop-api",
    )

    from app.content.embedder import FakeEmbedder
    from app.content.retrieval import RetrievalService

    async with session_factory() as db:
        retrieval_svc = await RetrievalService.from_db(session=db, embedder=FakeEmbedder())

    diagnoser = DiagnoserService(llm_client=fake_llm, retrieval_service=retrieval_svc)
    orchestrator = Orchestrator(
        llm_client=fake_llm,
        diagnoser=diagnoser,
        mastery_service=MasteryService(),
        history_service=HistoryService(),
        settings=settings,
    )

    yield {
        "orchestrator": orchestrator,
        "llm": fake_llm,
        "session_factory": session_factory,
        "user_id": test_user_id,
        "session_id": session.id,
        "concept_id": "c_target",
    }

    await engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_end_to_end_turn_and_event_order(
    orchestrator_fixture: dict[str, Any],
) -> None:
    """Full turn execution verifies event order: strategy -> mastery_update -> token -> done."""
    orch: Orchestrator = orchestrator_fixture["orchestrator"]
    llm: FakeLLMClient = orchestrator_fixture["llm"]
    session_factory = orchestrator_fixture["session_factory"]
    user_id = orchestrator_fixture["user_id"]
    session_id = orchestrator_fixture["session_id"]

    # Queue diagnosis result: correct, high confidence
    diag_tool_call = {
        "name": "diagnose_learner_message",
        "input": {
            "understanding": "correct",
            "confidence": 0.95,
            "misconception_id": None,
            "emotional_state": "engaged",
            "needs_verification": False,
        },
    }
    llm.queue_completion(LLMResult(content="", tool_calls=[diag_tool_call]))
    # Queue streaming reply tokens
    llm.queue_stream(["Great ", "job! ", "What ", "happens ", "next?"])

    events: list[OrchestratorEvent] = []
    async with session_factory() as db:
        session = (await db.execute(select(Session).where(Session.id == session_id))).scalar_one()
        concept = (
            await db.execute(select(Concept).where(Concept.id == session.concept_id))
        ).scalar_one()
        problem = (await db.execute(select(Problem).where(Problem.id == "p_accel_1"))).scalar_one()

        async for event in orch.run_turn(
            session=session,
            concept=concept,
            learner_message="The acceleration is 4 m/s^2 because a = F / m.",
            user_id=user_id,
            db=db,
            problem=problem,
            session_factory=session_factory,
        ):
            events.append(event)

    event_types = [e.event_type for e in events]
    # Check that events exist and are in the expected order
    assert "strategy" in event_types
    assert "mastery_update" in event_types
    assert "token" in event_types
    assert "done" in event_types

    # Event ordering assertions
    strat_idx = event_types.index("strategy")
    mastery_idx = event_types.index("mastery_update")
    first_token_idx = event_types.index("token")
    done_idx = event_types.index("done")

    assert strat_idx < first_token_idx
    assert mastery_idx < first_token_idx
    assert first_token_idx < done_idx
    assert done_idx == len(events) - 1

    # Verify database persistence
    async with session_factory() as db:
        turns_stmt = select(Turn).where(Turn.session_id == session_id).order_by(Turn.created_at)
        turns = list((await db.execute(turns_stmt)).scalars().all())
        assert len(turns) == 2
        # User turn
        assert turns[0].role == "user"
        assert turns[0].diagnosis["understanding"] == "correct"
        # Assistant turn
        assert turns[1].role == "assistant"
        assert turns[1].content == "Great job! What happens next?"
        assert turns[1].leak_suspected is False


@pytest.mark.asyncio
async def test_diagnoser_fallback_completes_turn_with_guided_hint(
    orchestrator_fixture: dict[str, Any],
) -> None:
    """Diagnoser timeout/failure triggers fallback diagnosis, selecting guided_hint."""
    orch: Orchestrator = orchestrator_fixture["orchestrator"]
    llm: FakeLLMClient = orchestrator_fixture["llm"]
    session_factory = orchestrator_fixture["session_factory"]
    user_id = orchestrator_fixture["user_id"]
    session_id = orchestrator_fixture["session_id"]

    # Queue an LLM error on diagnosis completion
    llm.queue_error(LLMTimeoutError("Diagnosis model timed out"))
    # Queue streaming reply tokens
    llm.queue_stream(["Let's ", "think ", "about ", "force."])

    events: list[OrchestratorEvent] = []
    async with session_factory() as db:
        session = (await db.execute(select(Session).where(Session.id == session_id))).scalar_one()
        concept = (
            await db.execute(select(Concept).where(Concept.id == session.concept_id))
        ).scalar_one()

        async for event in orch.run_turn(
            session=session,
            concept=concept,
            learner_message="I'm not quite sure how to start.",
            user_id=user_id,
            db=db,
            session_factory=session_factory,
        ):
            events.append(event)

    strategy_events = [e for e in events if e.event_type == "strategy"]
    assert len(strategy_events) == 1
    assert strategy_events[0].data["strategy"] == StrategyType.GUIDED_HINT.value

    done_events = [e for e in events if e.event_type == "done"]
    assert len(done_events) == 1


@pytest.mark.asyncio
async def test_atomicity_under_injected_mid_stream_failure(
    orchestrator_fixture: dict[str, Any],
) -> None:
    """Injected failure mid-stream ensures learner turn and mastery remain safely persisted."""
    orch: Orchestrator = orchestrator_fixture["orchestrator"]
    llm: FakeLLMClient = orchestrator_fixture["llm"]
    session_factory = orchestrator_fixture["session_factory"]
    user_id = orchestrator_fixture["user_id"]
    session_id = orchestrator_fixture["session_id"]

    # Successful diagnosis
    diag_call = {
        "name": "diagnose_learner_message",
        "input": {
            "understanding": "correct",
            "confidence": 0.90,
            "misconception_id": None,
            "emotional_state": "engaged",
        },
    }
    llm.queue_completion(LLMResult(content="", tool_calls=[diag_call]))
    # Queue error during token stream
    llm.queue_stream_error(LLMTimeoutError("Stream severed mid-transit"))

    events: list[OrchestratorEvent] = []
    async with session_factory() as db:
        session = (await db.execute(select(Session).where(Session.id == session_id))).scalar_one()
        concept = (
            await db.execute(select(Concept).where(Concept.id == session.concept_id))
        ).scalar_one()

        async for event in orch.run_turn(
            session=session,
            concept=concept,
            learner_message="The net force determines acceleration.",
            user_id=user_id,
            db=db,
            session_factory=session_factory,
        ):
            events.append(event)

    # An error event must have been emitted
    error_events = [e for e in events if e.event_type == "error"]
    assert len(error_events) == 1
    assert error_events[0].data["code"] == "LLM_TIMEOUT"

    # Transaction 1 guarantee: Learner turn and mastery ARE saved in database despite stream failure
    async with session_factory() as db:
        turns_stmt = select(Turn).where(Turn.session_id == session_id)
        turns = list((await db.execute(turns_stmt)).scalars().all())
        assert len(turns) == 1
        assert turns[0].role == "user"

        mastery_stmt = select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.concept_id == concept.id,
        )
        mastery = (await db.execute(mastery_stmt)).scalar_one()
        assert mastery.attempts == 1


@pytest.mark.asyncio
async def test_output_guard_detects_answer_leak(orchestrator_fixture: dict[str, Any]) -> None:
    """If tutor reply leaks known answer in Socratic mode, flag leak_suspected=True."""
    orch: Orchestrator = orchestrator_fixture["orchestrator"]
    llm: FakeLLMClient = orchestrator_fixture["llm"]
    session_factory = orchestrator_fixture["session_factory"]
    user_id = orchestrator_fixture["user_id"]
    session_id = orchestrator_fixture["session_id"]

    # Partial understanding -> guided_hint mode
    diag_call = {
        "name": "diagnose_learner_message",
        "input": {
            "understanding": "partial",
            "confidence": 0.80,
            "misconception_id": None,
            "emotional_state": "engaged",
        },
    }
    llm.queue_completion(LLMResult(content="", tool_calls=[diag_call]))
    # Problem answer is 4.0. Tutor accidentally streams the exact answer:
    llm.queue_stream(["The ", "answer ", "is ", "4.0", " m/s^2."])

    events: list[OrchestratorEvent] = []
    async with session_factory() as db:
        session = (await db.execute(select(Session).where(Session.id == session_id))).scalar_one()
        concept = (
            await db.execute(select(Concept).where(Concept.id == session.concept_id))
        ).scalar_one()
        problem = (await db.execute(select(Problem).where(Problem.id == "p_accel_1"))).scalar_one()

        async for event in orch.run_turn(
            session=session,
            concept=concept,
            learner_message="Is acceleration 2 or something else?",
            user_id=user_id,
            db=db,
            problem=problem,
            session_factory=session_factory,
        ):
            events.append(event)

    done_events = [e for e in events if e.event_type == "done"]
    assert len(done_events) == 1
    assert done_events[0].data["leak_suspected"] is True

    # Verify persisted in database
    async with session_factory() as db:
        assistant_turn = (
            await db.execute(
                select(Turn).where(Turn.session_id == session_id, Turn.role == "assistant")
            )
        ).scalar_one()
        assert assistant_turn.leak_suspected is True


@pytest.mark.asyncio
async def test_scripted_conversation_strategy_transitions(
    orchestrator_fixture: dict[str, Any],
) -> None:
    """Scripted conversation demonstrates strategy adapting to mastery and emotions."""
    orch: Orchestrator = orchestrator_fixture["orchestrator"]
    llm: FakeLLMClient = orchestrator_fixture["llm"]
    session_factory = orchestrator_fixture["session_factory"]
    user_id = orchestrator_fixture["user_id"]
    session_id = orchestrator_fixture["session_id"]

    strategies_chosen: list[str] = []

    async def execute_turn(
        user_msg: str,
        understanding: str,
        confidence: float,
        emotional_state: str = "engaged",
        misconception_id: str | None = None,
    ) -> str:
        diag_call = {
            "name": "diagnose_learner_message",
            "input": {
                "understanding": understanding,
                "confidence": confidence,
                "misconception_id": misconception_id,
                "emotional_state": emotional_state,
            },
        }
        llm.queue_completion(LLMResult(content="", tool_calls=[diag_call]))
        llm.queue_stream(["Reply ", "turn."])

        strategy_val = ""
        async with session_factory() as db:
            session = (
                await db.execute(select(Session).where(Session.id == session_id))
            ).scalar_one()
            concept = (
                await db.execute(select(Concept).where(Concept.id == session.concept_id))
            ).scalar_one()

            async for event in orch.run_turn(
                session=session,
                concept=concept,
                learner_message=user_msg,
                user_id=user_id,
                db=db,
                session_factory=session_factory,
            ):
                if event.event_type == "strategy":
                    strategy_val = event.data["strategy"]
        return strategy_val

    # Seed prerequisite as mastered initially so target concept mastery controls strategy
    async with session_factory() as db:
        prereq_mastery = Mastery(
            user_id=user_id,
            concept_id="c_prereq",
            p_known=0.85,
            attempts=5,
        )
        db.add(prereq_mastery)
        await db.commit()

    # Turn 1: Initial state has low baseline mastery (< 0.35) -> WORKED_EXAMPLE
    s1 = await execute_turn("Hello tutor", understanding="unclear", confidence=0.0)
    strategies_chosen.append(s1)
    assert s1 == StrategyType.WORKED_EXAMPLE.value

    # Turn 2: Learner grasps concept, mastery updates from 0.20 -> 0.44 (< 0.70) -> GUIDED_HINT
    s2 = await execute_turn("F = m * a", understanding="correct", confidence=0.90)
    strategies_chosen.append(s2)
    assert s2 == StrategyType.GUIDED_HINT.value

    # Turn 3: Learner exhibits a specific misconception -> COGNITIVE_CONFLICT
    s3 = await execute_turn(
        "Objects stop when force runs out",
        understanding="incorrect",
        confidence=0.85,
        misconception_id="m_force_motion",
    )
    strategies_chosen.append(s3)
    assert s3 == StrategyType.COGNITIVE_CONFLICT.value

    # Turn 4: Learner gets frustrated -> WORKED_EXAMPLE
    s4 = await execute_turn(
        "I hate this, I don't understand!",
        understanding="incorrect",
        confidence=0.80,
        emotional_state="frustrated",
    )
    strategies_chosen.append(s4)
    assert s4 == StrategyType.WORKED_EXAMPLE.value

    # Turn 5: Prerequisite gap identified -> PREREQUISITE_REVIEW
    async with session_factory() as db:
        pm = (
            await db.execute(
                select(Mastery).where(Mastery.user_id == user_id, Mastery.concept_id == "c_prereq")
            )
        ).scalar_one()
        pm.p_known = 0.20
        await db.commit()

    s5 = await execute_turn(
        "Coordinate direction is confusing", understanding="unclear", confidence=0.0
    )
    strategies_chosen.append(s5)
    assert s5 == StrategyType.PREREQUISITE_REVIEW.value

    # Turn 6: Prerequisite resolved, learner achieves high mastery -> SOCRATIC_CHALLENGE
    async with session_factory() as db:
        pm = (
            await db.execute(
                select(Mastery).where(Mastery.user_id == user_id, Mastery.concept_id == "c_prereq")
            )
        ).scalar_one()
        pm.p_known = 0.90
        await db.commit()

    await execute_turn(
        "Force is zero so acceleration is zero", understanding="correct", confidence=0.95
    )
    await execute_turn("Velocity remains constant", understanding="correct", confidence=0.95)
    s6 = await execute_turn("Inertia maintains motion", understanding="correct", confidence=0.95)
    strategies_chosen.append(s6)
    assert s6 == StrategyType.SOCRATIC_CHALLENGE.value


@pytest.mark.asyncio
async def test_orchestrator_records_activity_event_on_gradable_turn(
    orchestrator_fixture: dict[str, Any],
) -> None:
    session_factory = orchestrator_fixture["session_factory"]
    user_id = orchestrator_fixture["user_id"]
    orchestrator = orchestrator_fixture["orchestrator"]
    llm = orchestrator_fixture["llm"]
    session_id = orchestrator_fixture["session_id"]

    # Queue diagnoser response (correct answer) and tutor response
    diag_tool = {
        "name": "diagnose_learner_message",
        "input": {
            "understanding": "correct",
            "misconception_id": None,
            "confidence": 0.90,
            "needs_verification": False,
            "extracted_answer": None,
            "emotional_state": "engaged",
        },
    }
    llm.queue_completion(LLMResult(content="", tool_calls=[diag_tool]))
    llm.queue_stream(["Excellent! ", "That is entirely correct."])

    events = []
    async with session_factory() as db:
        session = (await db.execute(select(Session).where(Session.id == session_id))).scalar_one()
        concept = (
            await db.execute(select(Concept).where(Concept.id == session.concept_id))
        ).scalar_one()

        async for ev in orchestrator.run_turn(
            session=session,
            concept=concept,
            learner_message="An object at rest stays at rest unless a force acts on it.",
            user_id=user_id,
            db=db,
            session_factory=session_factory,
        ):
            events.append(ev)

    # Verify activity event was recorded
    async with session_factory() as db:
        act_stmt = select(ActivityEvent).where(
            ActivityEvent.user_id == user_id,
            ActivityEvent.kind == "tutor_turn_gradable",
        )
        act_res = await db.execute(act_stmt)
        act_event = act_res.scalar_one_or_none()
        assert act_event is not None
        assert act_event.ref_type == "turn"
        assert act_event.meta.get("concept_id") == "c_target"
