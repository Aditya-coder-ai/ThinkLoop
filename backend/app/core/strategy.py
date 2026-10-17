"""Rule-based pedagogical strategy selection engine."""

import logging
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import Settings
from app.schemas.diagnosis import Diagnosis

logger = logging.getLogger(__name__)


class StrategyType(StrEnum):
    """Pedagogical teaching strategies."""

    WORKED_EXAMPLE = "worked_example"
    GUIDED_HINT = "guided_hint"
    SOCRATIC_CHALLENGE = "socratic_challenge"
    COGNITIVE_CONFLICT = "cognitive_conflict"
    PREREQUISITE_REVIEW = "prerequisite_review"


STRATEGY_PROMPT_VERSIONS: dict[StrategyType, str] = {
    StrategyType.WORKED_EXAMPLE: "strategy_worked_example_v1",
    StrategyType.GUIDED_HINT: "strategy_guided_hint_v1",
    StrategyType.SOCRATIC_CHALLENGE: "strategy_socratic_challenge_v1",
    StrategyType.COGNITIVE_CONFLICT: "strategy_cognitive_conflict_v1",
    StrategyType.PREREQUISITE_REVIEW: "strategy_prerequisite_review_v1",
}


@dataclass(frozen=True)
class StrategyContext:
    """Contextual pedagogical signals from knowledge graph and learner session."""

    has_weak_prerequisite: bool = False
    weak_prerequisite_id: str | None = None
    weak_prerequisite_title: str | None = None
    conflict_prompt: str | None = None
    active_problem_id: str | None = None


def choose_strategy(
    mastery: float,
    diagnosis: Diagnosis,
    context: StrategyContext | None = None,
    settings: Settings | None = None,
) -> StrategyType:
    """Select pedagogical strategy using strict deterministic rule priority.

    Rules Priority:
    1. Fallback diagnosis (system failure / timeout) -> guided_hint
    2. Emotional frustration -> worked_example
    3. Confident misconception detected -> cognitive_conflict (via misconception conflict prompt)
    4. Weak prerequisite gap identified -> prerequisite_review
    5. Low mastery (< 0.35) -> worked_example
    6. Intermediate mastery (< 0.70) -> guided_hint
    7. High mastery (>= 0.70) -> socratic_challenge
    """
    low_mastery_threshold = settings.strategy_mastery_low_threshold if settings else 0.35
    high_mastery_threshold = settings.strategy_mastery_high_threshold if settings else 0.70
    confidence_threshold = settings.diagnoser_confidence_threshold if settings else 0.70

    # 1. Fallback diagnosis
    if diagnosis.diagnosis_fallback:
        logger.info("Strategy selected: GUIDED_HINT (due to diagnosis fallback)")
        return StrategyType.GUIDED_HINT

    # 2. Learner frustration
    if diagnosis.emotional_state == "frustrated":
        logger.info("Strategy selected: WORKED_EXAMPLE (due to learner frustration)")
        return StrategyType.WORKED_EXAMPLE

    # 3. Detected misconception with confidence >= threshold
    if diagnosis.misconception_id is not None and diagnosis.confidence >= confidence_threshold:
        logger.info(
            "Strategy selected: COGNITIVE_CONFLICT (misconception=%s, conf=%.2f)",
            diagnosis.misconception_id,
            diagnosis.confidence,
        )
        return StrategyType.COGNITIVE_CONFLICT

    # 4. Weak prerequisite identified as root gap
    if context is not None and context.has_weak_prerequisite:
        logger.info(
            "Strategy selected: PREREQUISITE_REVIEW (weak_prereq=%s)",
            context.weak_prerequisite_id,
        )
        return StrategyType.PREREQUISITE_REVIEW

    # 5. Low mastery (< 0.35)
    if mastery < low_mastery_threshold:
        logger.info(
            "Strategy selected: WORKED_EXAMPLE (low mastery=%.3f < %.2f)",
            mastery,
            low_mastery_threshold,
        )
        return StrategyType.WORKED_EXAMPLE

    # 6. Intermediate mastery (< 0.70)
    if mastery < high_mastery_threshold:
        logger.info(
            "Strategy selected: GUIDED_HINT (mid mastery=%.3f < %.2f)",
            mastery,
            high_mastery_threshold,
        )
        return StrategyType.GUIDED_HINT

    # 7. High mastery (>= 0.70)
    logger.info(
        "Strategy selected: SOCRATIC_CHALLENGE (high mastery=%.3f >= %.2f)",
        mastery,
        high_mastery_threshold,
    )
    return StrategyType.SOCRATIC_CHALLENGE


def extract_answer_strings(answer_spec: dict[str, Any] | None) -> list[str]:
    """Extract literal target answer string representations from answer_spec for leak detection."""
    if not answer_spec:
        return []
    spec_type = answer_spec.get("type")
    answers: list[str] = []
    if spec_type == "numeric":
        val = answer_spec.get("value")
        if val is not None:
            answers.append(str(val).strip())
    elif spec_type == "symbolic":
        expr = answer_spec.get("expression")
        if expr:
            answers.append(str(expr).strip())
    elif spec_type == "multiple_choice":
        options = answer_spec.get("options", [])
        idx = answer_spec.get("correct_index")
        if isinstance(idx, int) and 0 <= idx < len(options):
            answers.append(str(options[idx]).strip())
    return [a for a in answers if a]


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=16)
def _load_prompt_template(filename: str) -> str:
    path = _PROMPT_DIR / filename
    return path.read_text(encoding="utf-8")


def render_strategy_prompt(
    strategy: StrategyType,
    concept_title: str,
    concept_description: str,
    problem_statement: str | None = None,
    problem_answer_spec: dict[str, Any] | None = None,
    conflict_prompt: str | None = None,
    weak_prerequisite_title: str | None = None,
    weak_prerequisite_description: str | None = None,
) -> str:
    """Render versioned strategy system prompt, enforcing answer privacy in Socratic/hint modes."""
    template_name = f"{STRATEGY_PROMPT_VERSIONS[strategy]}.md"
    template = _load_prompt_template(template_name)

    # Format problem context safely (never includes answer_spec)
    problem_context = ""
    if problem_statement:
        problem_context = f"\n## Active Practice Problem\n- Statement: {problem_statement}"

    prompt = template.format(
        concept_title=concept_title,
        concept_description=concept_description,
        problem_context=problem_context,
        conflict_prompt=conflict_prompt or "Consider what happens under extreme conditions.",
        weak_prerequisite_title=weak_prerequisite_title or "Foundational Concept",
        weak_prerequisite_description=weak_prerequisite_description or "Prerequisite foundation.",
    )

    # Strict invariant check: Socratic and hint modes must never contain answers
    if (
        strategy
        in (
            StrategyType.GUIDED_HINT,
            StrategyType.SOCRATIC_CHALLENGE,
            StrategyType.COGNITIVE_CONFLICT,
            StrategyType.PREREQUISITE_REVIEW,
        )
        and problem_answer_spec
    ):
        answer_strings = extract_answer_strings(problem_answer_spec)
        for ans in answer_strings:
            # Check for literal answer leak in rendered system prompt
            if len(ans) > 1 and ans.lower() in prompt.lower():
                err_msg = (
                    f"Answer privacy invariant violated: answer '{ans}' detected in "
                    f"{strategy.value} prompt"
                )
                raise ValueError(err_msg)

    return prompt
