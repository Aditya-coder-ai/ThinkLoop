"""History service for managing dialogue turns window and running summary."""

from collections.abc import Sequence
from dataclasses import dataclass

from app.db.models import Turn
from app.services.llm import LLMMessage


@dataclass
class HistoryWindow:
    """Window of recent dialogue turns with optional running summary."""

    recent_turns: list[Turn]
    running_summary: str | None = None


class HistoryService:
    """Manages dialogue history truncation, summarization interface, and LLM message formatting."""

    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max_turns

    def build_history_window(
        self,
        turns: Sequence[Turn],
        running_summary: str | None = None,
    ) -> HistoryWindow:
        """Extract the most recent N turns in chronological order."""
        turn_list = list(turns)
        recent = turn_list[-self.max_turns :] if len(turn_list) > self.max_turns else turn_list
        return HistoryWindow(recent_turns=recent, running_summary=running_summary)

    def format_for_llm(
        self,
        turns: Sequence[Turn],
        running_summary: str | None = None,
    ) -> list[LLMMessage]:
        """Format historical turns and summary into LLM messages."""
        window = self.build_history_window(turns=turns, running_summary=running_summary)
        messages: list[LLMMessage] = []

        if window.running_summary:
            messages.append(
                LLMMessage(
                    role="user",
                    content=(
                        f"Context from previous conversation summary:\n{window.running_summary}"
                    ),
                )
            )

        for turn in window.recent_turns:
            role = "assistant" if turn.role in ("assistant", "tutor") else "user"
            messages.append(LLMMessage(role=role, content=turn.content))

        return messages
