"""Basic Socratic dialogue responder."""

from collections.abc import AsyncIterator
from pathlib import Path

from app.db.models import Concept
from app.services.llm import LLMClient, LLMMessage

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
RESPONDER_BASIC_PROMPT_PATH = PROMPTS_DIR / "responder_basic_v1.md"


class ResponderService:
    """Coordinates prompt assembly and LLM streaming for basic tutor replies."""

    PROMPT_VERSION = "responder_basic_v1"

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client
        self._prompt_template = self._load_template()

    def _load_template(self) -> str:
        """Load versioned Markdown prompt template."""
        if RESPONDER_BASIC_PROMPT_PATH.exists():
            return RESPONDER_BASIC_PROMPT_PATH.read_text(encoding="utf-8")
        return (
            "You are Thinkloop, an AI Socratic tutor. "
            "Help the student understand {concept_title}. Never give away the answer directly. "
            "Ask one focused question at a time."
        )

    def render_system_prompt(self, concept: Concept) -> str:
        """Render prompt with concept details."""
        return self._prompt_template.format(
            concept_id=concept.id,
            concept_title=concept.title,
            concept_description=concept.description,
        )

    async def stream_reply(
        self,
        concept: Concept,
        messages: list[LLMMessage],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream reply tokens from LLM client."""
        system_prompt = self.render_system_prompt(concept)
        async for token in self.llm_client.stream(
            messages=messages,
            system=system_prompt,
            model=model,
        ):
            yield token
