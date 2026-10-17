"""Unit tests for rule-based pedagogical strategy selection."""

import pytest

from app.config import Settings
from app.core.strategy import StrategyContext, StrategyType, choose_strategy
from app.schemas.diagnosis import Diagnosis


def make_diagnosis(
    understanding: str = "correct",
    confidence: float = 0.9,
    misconception_id: str | None = None,
    emotional_state: str = "engaged",
    diagnosis_fallback: bool = False,
) -> Diagnosis:
    """Helper to construct a Diagnosis object."""
    return Diagnosis(
        understanding=understanding,  # type: ignore[arg-type]
        confidence=confidence,
        misconception_id=misconception_id,
        emotional_state=emotional_state,  # type: ignore[arg-type]
        diagnosis_fallback=diagnosis_fallback,
    )


class TestChooseStrategy:
    """Table-driven test suite validating strategy rules and boundary transitions."""

    def test_diagnosis_fallback_returns_guided_hint(self) -> None:
        """Fallback diagnosis when system times out always selects guided_hint."""
        diag = make_diagnosis(diagnosis_fallback=True)
        strategy = choose_strategy(mastery=0.90, diagnosis=diag)
        assert strategy == StrategyType.GUIDED_HINT

    def test_frustrated_emotion_returns_worked_example(self) -> None:
        """Frustrated learner always receives a worked example regardless of mastery."""
        diag = make_diagnosis(emotional_state="frustrated")
        strategy = choose_strategy(mastery=0.85, diagnosis=diag)
        assert strategy == StrategyType.WORKED_EXAMPLE

    def test_detected_misconception_returns_cognitive_conflict(self) -> None:
        """Misconception with confidence >= threshold triggers cognitive_conflict."""
        diag = make_diagnosis(misconception_id="m_force_velocity", confidence=0.75)
        strategy = choose_strategy(mastery=0.60, diagnosis=diag)
        assert strategy == StrategyType.COGNITIVE_CONFLICT

    def test_detected_misconception_exact_threshold(self) -> None:
        """Exact confidence threshold (0.70) triggers cognitive_conflict."""
        diag = make_diagnosis(misconception_id="m_force_velocity", confidence=0.70)
        strategy = choose_strategy(mastery=0.80, diagnosis=diag)
        assert strategy == StrategyType.COGNITIVE_CONFLICT

    def test_low_confidence_misconception_falls_through(self) -> None:
        """Misconception with confidence < 0.70 does not trigger cognitive_conflict."""
        diag = make_diagnosis(misconception_id="m_force_velocity", confidence=0.69)
        # Should fall through to mastery: 0.80 >= 0.70 -> socratic_challenge
        strategy = choose_strategy(mastery=0.80, diagnosis=diag)
        assert strategy == StrategyType.SOCRATIC_CHALLENGE

    def test_weak_prerequisite_triggers_review(self) -> None:
        """Identified weak prerequisite gap triggers prerequisite_review."""
        diag = make_diagnosis()
        ctx = StrategyContext(has_weak_prerequisite=True, weak_prerequisite_id="c_vectors")
        strategy = choose_strategy(mastery=0.80, diagnosis=diag, context=ctx)
        assert strategy == StrategyType.PREREQUISITE_REVIEW

    @pytest.mark.parametrize(
        ("mastery", "expected"),
        [
            (0.00, StrategyType.WORKED_EXAMPLE),
            (0.20, StrategyType.WORKED_EXAMPLE),
            (0.349, StrategyType.WORKED_EXAMPLE),
            (0.35, StrategyType.GUIDED_HINT),
            (0.50, StrategyType.GUIDED_HINT),
            (0.699, StrategyType.GUIDED_HINT),
            (0.70, StrategyType.SOCRATIC_CHALLENGE),
            (0.85, StrategyType.SOCRATIC_CHALLENGE),
            (1.00, StrategyType.SOCRATIC_CHALLENGE),
        ],
    )
    def test_mastery_boundaries(self, mastery: float, expected: StrategyType) -> None:
        """Strict mastery boundaries transition cleanly at 0.35 and 0.70."""
        diag = make_diagnosis()
        strategy = choose_strategy(mastery=mastery, diagnosis=diag)
        assert strategy == expected

    def test_custom_settings_thresholds(self) -> None:
        """Custom configured thresholds are respected."""
        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            REDIS_URL="redis://localhost:6379/0",
            AUTH_JWKS_URL="https://auth.thinkloop.ai/.well-known/jwks.json",
            AUTH_ISSUER="https://auth.thinkloop.ai",
            AUTH_AUDIENCE="thinkloop-api",
            STRATEGY_MASTERY_LOW_THRESHOLD=0.25,
            STRATEGY_MASTERY_HIGH_THRESHOLD=0.80,
            DIAGNOSER_CONFIDENCE_THRESHOLD=0.85,
        )
        diag = make_diagnosis(misconception_id="m1", confidence=0.80)
        # Confidence 0.80 is < custom threshold 0.85, so cognitive conflict should NOT trigger
        # Mastery 0.30 is > custom low threshold 0.25 and < custom high 0.80 -> guided_hint
        strategy = choose_strategy(mastery=0.30, diagnosis=diag, settings=settings)
        assert strategy == StrategyType.GUIDED_HINT
