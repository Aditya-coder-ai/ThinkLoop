from unittest.mock import MagicMock

import pytest

from app.content.retrieval import MisconceptionSearchResult, RetrievalService
from app.core.diagnoser import DiagnoserService, MisconceptionEventManager
from app.db.models import Concept
from app.services.llm import FakeLLMClient, LLMResult, LLMTimeoutError, TokenUsage


@pytest.fixture
def sample_concept() -> Concept:
    """Fixture providing a test Concept entity."""
    return Concept(
        id="c1",
        domain="physics",
        topic="mechanics",
        title="Newton's First Law",
        description="An extensive description of Newton's first law of motion.",
        difficulty=1,
        schema_version=1,
        is_active=True,
        content_hash="h1",
    )


@pytest.fixture
def mock_retrieval() -> MagicMock:
    """Mock RetrievalService returning candidate misconceptions."""
    retrieval = MagicMock(spec=RetrievalService)
    retrieval.find_misconceptions.return_value = [
        MisconceptionSearchResult(
            misconception_id="m1",
            concept_id="c1",
            statement="Constant velocity requires constant force",
            score=0.85,
        ),
        MisconceptionSearchResult(
            misconception_id="m2",
            concept_id="c1",
            statement="Inertia is a force",
            score=0.72,
        ),
    ]
    return retrieval


@pytest.mark.asyncio
async def test_diagnoser_parses_valid_tool_output(
    sample_concept: Concept, mock_retrieval: MagicMock
) -> None:
    """Diagnoser parses structured tool call into Diagnosis model."""
    fake_llm = FakeLLMClient()
    fake_llm.queue_completion(
        LLMResult(
            tool_calls=[
                {
                    "name": "diagnose_learner_message",
                    "input": {
                        "understanding": "incorrect",
                        "misconception_id": "m1",
                        "confidence": 0.95,
                        "needs_verification": False,
                        "extracted_answer": None,
                        "emotional_state": "confused",
                    },
                }
            ],
            usage=TokenUsage(input_tokens=50, output_tokens=30),
        )
    )

    diagnoser = DiagnoserService(llm_client=fake_llm, retrieval_service=mock_retrieval)
    diagnosis = await diagnoser.diagnose(
        concept=sample_concept,
        learner_message="A rocket needs fuel to keep moving in space.",
    )

    assert diagnosis.understanding == "incorrect"
    assert diagnosis.misconception_id == "m1"
    assert diagnosis.confidence == 0.95
    assert diagnosis.needs_verification is False
    assert diagnosis.emotional_state == "confused"
    assert diagnosis.diagnosis_fallback is False


@pytest.mark.asyncio
async def test_diagnoser_discards_hallucinated_misconception_id(
    sample_concept: Concept, mock_retrieval: MagicMock
) -> None:
    """Diagnoser discards any misconception_id not present in candidate retrieval list."""
    fake_llm = FakeLLMClient()
    fake_llm.queue_completion(
        LLMResult(
            tool_calls=[
                {
                    "name": "diagnose_learner_message",
                    "input": {
                        "understanding": "incorrect",
                        "misconception_id": "hallucinated_misconception_999",
                        "confidence": 0.8,
                        "needs_verification": False,
                        "emotional_state": "engaged",
                    },
                }
            ]
        )
    )

    diagnoser = DiagnoserService(llm_client=fake_llm, retrieval_service=mock_retrieval)
    diagnosis = await diagnoser.diagnose(
        concept=sample_concept,
        learner_message="Force creates motion.",
    )

    # Hallucinated ID must be discarded to None
    assert diagnosis.misconception_id is None
    assert diagnosis.understanding == "incorrect"
    assert diagnosis.diagnosis_fallback is False


@pytest.mark.asyncio
async def test_diagnoser_fallback_on_missing_or_malformed_tool_output(
    sample_concept: Concept, mock_retrieval: MagicMock
) -> None:
    """Diagnoser returns safe fallback on missing or malformed tool output."""
    fake_llm = FakeLLMClient()
    # Completion has no tool calls
    fake_llm.queue_completion(LLMResult(content="I am not returning a tool call."))

    diagnoser = DiagnoserService(llm_client=fake_llm, retrieval_service=mock_retrieval)
    diagnosis = await diagnoser.diagnose(
        concept=sample_concept,
        learner_message="I don't know.",
    )

    assert diagnosis.understanding == "unclear"
    assert diagnosis.confidence == 0.0
    assert diagnosis.emotional_state == "engaged"
    assert diagnosis.diagnosis_fallback is True


@pytest.mark.asyncio
async def test_diagnoser_fallback_on_timeout(
    sample_concept: Concept, mock_retrieval: MagicMock
) -> None:
    """Diagnoser returns safe fallback on LLM timeout."""
    fake_llm = FakeLLMClient()
    fake_llm.queue_error(LLMTimeoutError("FAST_MODEL timeout"))

    diagnoser = DiagnoserService(llm_client=fake_llm, retrieval_service=mock_retrieval)
    diagnosis = await diagnoser.diagnose(
        concept=sample_concept,
        learner_message="Let me think.",
    )

    assert diagnosis.understanding == "unclear"
    assert diagnosis.confidence == 0.0
    assert diagnosis.diagnosis_fallback is True


@pytest.mark.asyncio
async def test_diagnoser_passes_candidate_ids_to_llm(
    sample_concept: Concept, mock_retrieval: MagicMock
) -> None:
    """Candidate misconceptions passed to LLM tool definition contain only retrieved candidates."""
    fake_llm = FakeLLMClient()
    fake_llm.queue_completion(
        LLMResult(
            tool_calls=[
                {
                    "name": "diagnose_learner_message",
                    "input": {
                        "understanding": "correct",
                        "confidence": 0.9,
                        "emotional_state": "engaged",
                    },
                }
            ]
        )
    )

    diagnoser = DiagnoserService(llm_client=fake_llm, retrieval_service=mock_retrieval)
    await diagnoser.diagnose(concept=sample_concept, learner_message="Velocity is constant.")

    assert len(fake_llm.recorded_calls) == 1
    call = fake_llm.recorded_calls[0]
    tools = call["tools"]
    assert tools is not None
    # Verify candidate list was embedded in tool description or enum
    tool_schema = tools[0]["input_schema"]["properties"]["misconception_id"]
    assert "m1" in tool_schema.get("enum", [])
    assert "m2" in tool_schema.get("enum", [])


def test_misconception_event_state_machine_valid_transitions() -> None:
    """Event state machine validates legal transition: detected -> challenged -> resolved."""
    manager = MisconceptionEventManager()
    assert manager.is_valid_transition(current_status=None, new_status="detected") is True
    assert manager.is_valid_transition(current_status="detected", new_status="challenged") is True
    assert manager.is_valid_transition(current_status="challenged", new_status="resolved") is True
    assert manager.is_valid_transition(current_status="detected", new_status="resolved") is True


def test_misconception_event_state_machine_rejects_illegal_transitions() -> None:
    """Event state machine rejects illegal transition (e.g. resolved without prior detected)."""
    manager = MisconceptionEventManager()
    assert manager.is_valid_transition(current_status=None, new_status="resolved") is False
    assert manager.is_valid_transition(current_status=None, new_status="challenged") is False
    assert manager.is_valid_transition(current_status="resolved", new_status="detected") is False
