"""Pedagogical Diagnosis Engine and Misconception State Machine."""

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.retrieval import RetrievalService
from app.db.models import Concept, MisconceptionEvent
from app.schemas.diagnosis import Diagnosis
from app.services.llm import LLMClient, LLMMessage

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DIAGNOSER_PROMPT_PATH = PROMPTS_DIR / "diagnoser_v1.md"


class MisconceptionEventManager:
    """Manages misconception lifecycle state machine (detected -> challenged -> resolved)."""

    VALID_TRANSITIONS: dict[str | None, set[str]] = {
        None: {"detected"},
        "detected": {"challenged", "resolved"},
        "challenged": {"resolved"},
        "resolved": set(),
    }

    def is_valid_transition(self, current_status: str | None, new_status: str) -> bool:
        """Verify whether status transition is permissible under the state machine."""
        allowed = self.VALID_TRANSITIONS.get(current_status, set())
        return new_status in allowed

    async def get_latest_status(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        misconception_id: str,
    ) -> str | None:
        """Fetch the most recent status of a misconception within a session."""
        stmt = (
            select(MisconceptionEvent.status)
            .where(
                MisconceptionEvent.session_id == session_id,
                MisconceptionEvent.misconception_id == misconception_id,
            )
            .order_by(MisconceptionEvent.created_at.desc())
            .limit(1)
        )
        return (await db.execute(stmt)).scalar_one_or_none()

    async def record_event(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        misconception_id: str,
        new_status: str,
        turn_id: uuid.UUID | None = None,
    ) -> MisconceptionEvent | None:
        """Record a validated misconception event in the database."""
        current_status = await self.get_latest_status(
            db=db,
            session_id=session_id,
            misconception_id=misconception_id,
        )
        if not self.is_valid_transition(current_status=current_status, new_status=new_status):
            logger.warning(
                "Rejected illegal misconception event transition: current=%s, new=%s",
                current_status,
                new_status,
            )
            return None

        event = MisconceptionEvent(
            id=uuid.uuid4(),
            session_id=session_id,
            user_id=user_id,
            misconception_id=misconception_id,
            status=new_status,
            turn_id=turn_id,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event


class DiagnoserService:
    """Diagnoses learner messages using FAST_MODEL with tool-calling and candidate retrieval."""

    PROMPT_VERSION = "diagnoser_v1"

    def __init__(
        self,
        llm_client: LLMClient,
        retrieval_service: RetrievalService,
        fast_model: str = "claude-3-5-haiku-latest",
    ) -> None:
        self.llm_client = llm_client
        self.retrieval_service = retrieval_service
        self.fast_model = fast_model
        self._prompt_template = self._load_template()

    def _load_template(self) -> str:
        """Load versioned Markdown prompt template."""
        if DIAGNOSER_PROMPT_PATH.exists():
            return DIAGNOSER_PROMPT_PATH.read_text(encoding="utf-8")
        return (
            "Diagnose the learner's understanding and check for misconceptions. "
            "Concept: {concept_title}. Candidates: {candidate_misconceptions}"
        )

    def _build_tool_schema(self, candidate_ids: list[str]) -> dict[str, Any]:
        """Construct Anthropic-style tool definition with candidate IDs constrained."""
        misconception_id_prop: dict[str, Any] = {
            "type": ["string", "null"],
            "description": (
                "Identified candidate misconception ID from the Candidate list, or null if none."
            ),
        }
        if candidate_ids:
            misconception_id_prop["enum"] = candidate_ids + [None]

        return {
            "name": "diagnose_learner_message",
            "description": "Report structured diagnosis of the learner's message.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "understanding": {
                        "type": "string",
                        "enum": ["correct", "partial", "incorrect", "unclear"],
                        "description": "Conceptual correctness assessment",
                    },
                    "misconception_id": misconception_id_prop,
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Confidence score in this assessment",
                    },
                    "needs_verification": {
                        "type": "boolean",
                        "description": "True if an answer requires verification",
                    },
                    "extracted_answer": {
                        "type": ["string", "null"],
                        "description": "Extracted answer string if present",
                    },
                    "emotional_state": {
                        "type": "string",
                        "enum": ["engaged", "confused", "frustrated", "bored"],
                        "description": "Inferred emotional state",
                    },
                },
                "required": ["understanding", "confidence"],
            },
        }

    async def diagnose(
        self,
        concept: Concept,
        learner_message: str,
    ) -> Diagnosis:
        """Execute diagnosis on learner message."""
        # 1. Retrieve top candidate misconceptions
        candidate_ids: list[str] = []
        candidate_strings: list[str] = []
        try:
            candidates = self.retrieval_service.find_misconceptions(
                text=learner_message,
                concept_id=concept.id,
                include_prereqs=True,
                k=5,
            )
            for c in candidates:
                mid = c.misconception_id
                if mid:
                    candidate_ids.append(mid)
                    stmt = c.statement
                    candidate_strings.append(f"- ID `{mid}`: {stmt}")
        except Exception as e:
            logger.warning("Retrieval of candidate misconceptions failed: %s", e)

        candidate_text = (
            "\n".join(candidate_strings)
            if candidate_strings
            else "None available for this concept."
        )

        system_prompt = self._prompt_template.format(
            concept_id=concept.id,
            concept_title=concept.title,
            concept_description=concept.description,
            candidate_misconceptions=candidate_text,
        )

        tool_def = self._build_tool_schema(candidate_ids)
        messages = [
            LLMMessage(role="user", content=learner_message),
        ]

        try:
            result = await self.llm_client.complete(
                messages=messages,
                system=system_prompt,
                tools=[tool_def],
                tool_choice={"type": "tool", "name": "diagnose_learner_message"},
                model=self.fast_model,
            )

            # Look for the tool call
            tool_input: dict[str, Any] | None = None
            for call in result.tool_calls:
                if call.get("name") == "diagnose_learner_message":
                    tool_input = call.get("input", {})
                    break

            if not tool_input:
                logger.warning("Diagnoser FAST_MODEL did not return tool call, falling back")
                return Diagnosis(
                    understanding="unclear",
                    confidence=0.0,
                    emotional_state="engaged",
                    diagnosis_fallback=True,
                )

            # Strictly discard any misconception_id not in retrieved candidate list
            raw_mid = tool_input.get("misconception_id")
            validated_mid = raw_mid if raw_mid in candidate_ids else None

            # Safe confidence normalization
            raw_conf = float(tool_input.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, raw_conf))

            diagnosis = Diagnosis(
                understanding=tool_input.get("understanding", "unclear"),
                misconception_id=validated_mid,
                confidence=confidence,
                needs_verification=bool(tool_input.get("needs_verification", False)),
                extracted_answer=tool_input.get("extracted_answer"),
                emotional_state=tool_input.get("emotional_state", "engaged"),
                diagnosis_fallback=False,
            )
            return diagnosis

        except Exception as e:
            logger.error("Error executing diagnoser FAST_MODEL: %s", type(e).__name__)
            return Diagnosis(
                understanding="unclear",
                confidence=0.0,
                emotional_state="engaged",
                diagnosis_fallback=True,
            )
