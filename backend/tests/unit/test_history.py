"""Unit tests for HistoryService and history truncation."""

import uuid
from datetime import UTC, datetime

from app.db.models import Turn
from app.services.history import HistoryService


def test_history_service_truncation() -> None:
    """HistoryService keeps last N turns in chronological order."""
    session_id = uuid.uuid4()
    turns = [
        Turn(
            id=uuid.uuid4(),
            session_id=session_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}",
            created_at=datetime.now(UTC),
        )
        for i in range(10)
    ]

    service = HistoryService(max_turns=4)
    window = service.build_history_window(turns=turns, running_summary="Prior summary")

    assert len(window.recent_turns) == 4
    assert window.recent_turns[0].content == "Message 6"
    assert window.recent_turns[-1].content == "Message 9"
    assert window.running_summary == "Prior summary"


def test_history_service_formats_messages_for_llm() -> None:
    """History formats messages correctly for LLMClient consumption."""
    session_id = uuid.uuid4()
    turns = [
        Turn(
            id=uuid.uuid4(),
            session_id=session_id,
            role="user",
            content="What is velocity?",
            created_at=datetime.now(UTC),
        ),
        Turn(
            id=uuid.uuid4(),
            session_id=session_id,
            role="assistant",
            content="Velocity is the rate of change of displacement.",
            created_at=datetime.now(UTC),
        ),
    ]

    service = HistoryService(max_turns=10)
    messages = service.format_for_llm(turns=turns, running_summary="Student studying kinematics.")

    assert len(messages) == 3
    assert messages[0].role == "user"
    assert "Context from previous conversation" in messages[0].content
    assert messages[1].content == "What is velocity?"
    assert messages[2].content == "Velocity is the rate of change of displacement."
