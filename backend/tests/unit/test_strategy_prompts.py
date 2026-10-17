"""Unit tests validating strategy prompts and answer privacy invariants."""

import pytest

from app.core.strategy import (
    StrategyType,
    extract_answer_strings,
    render_strategy_prompt,
)


class TestStrategyPrompts:
    """Suite verifying prompt rendering and strict answer privacy invariants."""

    @pytest.mark.parametrize(
        "strategy",
        [
            StrategyType.WORKED_EXAMPLE,
            StrategyType.GUIDED_HINT,
            StrategyType.SOCRATIC_CHALLENGE,
            StrategyType.COGNITIVE_CONFLICT,
            StrategyType.PREREQUISITE_REVIEW,
        ],
    )
    def test_all_strategy_prompts_render_successfully(self, strategy: StrategyType) -> None:
        """Every strategy prompt template exists and renders without missing keys."""
        rendered = render_strategy_prompt(
            strategy=strategy,
            concept_title="Newton's Second Law",
            concept_description=(
                "Relates the net force applied on a body to its mass and acceleration."
            ),
            problem_statement="Calculate the acceleration of a 2 kg block pushed with 10 N.",
            conflict_prompt="Consider what happens in deep space with zero resistance.",
            weak_prerequisite_title="Vectors and Scalar Components",
            weak_prerequisite_description="Decomposing vectors into orthogonal components.",
        )
        assert "Newton's Second Law" in rendered
        assert "Thinkloop" in rendered
        # Assert each prompt enforces the single question rule
        assert "Single Question" in rendered or "ONE" in rendered

    @pytest.mark.parametrize(
        "strategy",
        [
            StrategyType.GUIDED_HINT,
            StrategyType.SOCRATIC_CHALLENGE,
            StrategyType.COGNITIVE_CONFLICT,
            StrategyType.PREREQUISITE_REVIEW,
        ],
    )
    def test_socratic_prompts_never_contain_answer_spec(self, strategy: StrategyType) -> None:
        """Socratic and hint mode prompts must never contain answer_spec fields or answers."""
        answer_spec = {
            "type": "numeric",
            "value": 42.5,
            "unit": "m/s^2",
            "tolerance": 0.01,
        }
        rendered = render_strategy_prompt(
            strategy=strategy,
            concept_title="Conservation of Energy",
            concept_description=(
                "Total mechanical energy in an isolated system remains constant over time."
            ),
            problem_statement="A 1 kg projectile is launched from ground level.",
            problem_answer_spec=answer_spec,
        )
        assert "answer_spec" not in rendered
        assert "42.5" not in rendered
        assert "tolerance" not in rendered

    def test_leak_prevention_raises_on_answer_in_prompt(self) -> None:
        """Prompt rendering raises ValueError if answer is accidentally injected."""
        leaky_answer_spec = {"type": "numeric", "value": "SuperSecretAnswer42"}
        with pytest.raises(ValueError, match="Answer privacy invariant violated"):
            render_strategy_prompt(
                strategy=StrategyType.SOCRATIC_CHALLENGE,
                concept_title="Gravity SuperSecretAnswer42",  # Contrived leak in concept
                concept_description="Description of gravitational acceleration.",
                problem_answer_spec=leaky_answer_spec,
            )

    def test_extract_answer_strings(self) -> None:
        """Verify answer string extraction across numeric, symbolic, and multiple choice."""
        assert extract_answer_strings(None) == []
        assert extract_answer_strings({"type": "numeric", "value": 9.8}) == ["9.8"]
        assert extract_answer_strings({"type": "symbolic", "expression": "m*g*h"}) == ["m*g*h"]
        mc_spec = {
            "type": "multiple_choice",
            "options": ["Velocity increases", "Velocity stays constant", "Stops instantly"],
            "correct_index": 1,
        }
        assert extract_answer_strings(mc_spec) == ["Velocity stays constant"]
