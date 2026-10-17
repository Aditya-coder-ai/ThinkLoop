"""Demonstration script streaming a dialogue conversation using FakeLLMClient.

Run with: uv run python -m scripts.chat_demo
"""

import asyncio
import sys
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.responder import ResponderService
from app.db.base import Base
from app.db.models import Concept, Session, Turn, User
from app.services.history import HistoryService
from app.services.llm import FakeLLMClient


async def main() -> None:
    print("=" * 60)
    print("THINKLOOP SOCRATIC CHAT STREAMING DEMO (FakeLLMClient)")
    print("=" * 60)

    # In-memory test database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # 1. Seed concept and user
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    concept_id = "newtons_first_law"

    async with session_factory() as db:
        user = User(id=user_id, auth_id="demo_user", email="demo@thinkloop.ai")
        concept = Concept(
            id=concept_id,
            domain="physics",
            topic="mechanics",
            title="Newton's First Law",
            description=(
                "An object at rest remains at rest, and an object in motion continues "
                "in motion with constant velocity, unless acted upon by a net external force."
            ),
            difficulty=1,
            schema_version=1,
            is_active=True,
            content_hash="demo_hash",
        )
        chat_session = Session(
            id=session_id,
            user_id=user_id,
            concept_id=concept_id,
            summary="Learner inquiring about moving objects in outer space.",
        )
        db.add_all([user, concept, chat_session])
        await db.commit()

    # 2. Configure FakeLLMClient with scripted replies
    fake_llm = FakeLLMClient()
    fake_llm.set_chunk_delay(0.04)  # Natural typing speed simulation
    fake_llm.queue_stream(
        [
            "Imagine ",
            "you ",
            "are ",
            "in ",
            "deep ",
            "space, ",
            "far ",
            "from ",
            "any ",
            "planets ",
            "or ",
            "gravity. ",
            "If ",
            "you ",
            "throw ",
            "a ",
            "baseball, ",
            "what ",
            "forces ",
            "are ",
            "acting ",
            "on ",
            "it ",
            "after ",
            "it ",
            "leaves ",
            "your ",
            "hand?",
        ]
    )

    responder = ResponderService(llm_client=fake_llm)
    history_service = HistoryService()

    # 3. Simulate learner turn
    learner_msg = "If an object is moving, doesn't it always need a force to keep it going?"
    print(f"\n[Learner]: {learner_msg}")

    async with session_factory() as db:
        user_turn = Turn(
            id=uuid.uuid4(),
            session_id=session_id,
            role="user",
            content=learner_msg,
        )
        db.add(user_turn)
        await db.commit()

    # 4. Stream tutor response
    print("\n[Tutor streaming]: ", end="", flush=True)

    async with session_factory() as db:
        chat_session = await db.get(Session, session_id)
        concept = await db.get(Concept, concept_id)
        assert chat_session is not None and concept is not None

        history_messages = history_service.format_for_llm(
            turns=[user_turn],
            running_summary=chat_session.summary,
        )

        accumulated: list[str] = []
        async for token in responder.stream_reply(concept=concept, messages=history_messages):
            sys.stdout.write(token)
            sys.stdout.flush()
            accumulated.append(token)

        full_reply = "".join(accumulated)
        tutor_turn = Turn(
            id=uuid.uuid4(),
            session_id=session_id,
            role="assistant",
            content=full_reply,
            prompt_versions={"responder": ResponderService.PROMPT_VERSION},
            token_usage={"tokens": len(full_reply.split())},
        )
        db.add(tutor_turn)
        await db.commit()

    print("\n\n" + "-" * 60)
    print("Turn completed and persisted successfully.")
    print("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
