"""Bayesian Knowledge Tracing (BKT) and Pedagogical Learner Model."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.clock import Clock


@dataclass(frozen=True)
class BKTParams:
    """Standard 4-parameter BKT parameters (prior is tracked per concept/user)."""

    p_learn: float = 0.15  # Probability of learning transition
    p_slip: float = 0.10  # Probability of slipping (false negative)
    p_guess: float = 0.20  # Probability of guessing (false positive)


DEFAULT_BKT_PARAMS = BKTParams()
MIN_P_KNOWN = 0.001
MAX_P_KNOWN = 0.999


def bkt_update(
    p_known: float,
    correct: bool,
    params: BKTParams | None = None,
) -> float:
    """Calculate the updated probability of mastery given a binary observation.

    Standard analytical formulation:
    1. Posterior update:
       P(L_t | obs=1) = (P(L_{t-1}) * (1 - p_slip)) /
                        (P(L_{t-1}) * (1 - p_slip) + (1 - P(L_{t-1})) * p_guess)
       P(L_t | obs=0) = (P(L_{t-1}) * p_slip) /
                        (P(L_{t-1}) * p_slip + (1 - P(L_{t-1})) * (1 - p_guess))
    2. Learning transition:
       P(L_t) = P(L_t | obs) + (1 - P(L_t | obs)) * p_learn
    3. Clamping to [0.001, 0.999] bounds.
    """
    bkt = params or DEFAULT_BKT_PARAMS
    # Clamp input prior
    p_prior = max(MIN_P_KNOWN, min(MAX_P_KNOWN, p_known))

    if correct:
        numerator = p_prior * (1.0 - bkt.p_slip)
        denominator = numerator + (1.0 - p_prior) * bkt.p_guess
    else:
        numerator = p_prior * bkt.p_slip
        denominator = numerator + (1.0 - p_prior) * (1.0 - bkt.p_guess)

    posterior = numerator / denominator if denominator > 0.0 else p_prior
    p_next = posterior + (1.0 - posterior) * bkt.p_learn

    return max(MIN_P_KNOWN, min(MAX_P_KNOWN, p_next))


def classify_mastery_state(p_known: float, attempts: int) -> str:
    """Classify mastery level into pedagogical categories: unseen, learning, mastered."""
    if attempts == 0 or p_known < 0.25:
        return "unseen"
    if p_known >= 0.85:
        return "mastered"
    return "learning"


def find_weak_or_stale_prerequisites(
    target_concept_id: str,
    prereq_graph: dict[str, list[str]],
    user_masteries: dict[str, dict[str, Any]],
    stale_threshold_days: int = 30,
    weak_threshold: float = 0.4,
    now: datetime | None = None,
    clock: Clock | None = None,
) -> list[dict[str, Any]]:
    """Traverse prerequisite DAG and identify concepts that are weak or stale.

    Args:
        target_concept_id: Root concept to inspect prerequisites for.
        prereq_graph: Mapping of concept_id -> list of direct prerequisite concept IDs.
        user_masteries: Mapping of concept_id -> {"p_known": float, "updated_at": datetime}.
        stale_threshold_days: Maximum days before mastery is flagged stale.
        weak_threshold: Minimum p_known below which prerequisite is flagged weak.
        now: Explicit reference timestamp for staleness calculations.
        clock: Optional Clock source to derive reference timestamp.

    Returns:
        List of flagged prerequisites with reasons ('weak' | 'stale').
    """
    # 1. Collect all transitive prerequisites using BFS
    visited: set[str] = set()
    queue = list(prereq_graph.get(target_concept_id, []))
    transitive_prereqs: list[str] = []

    while queue:
        curr = queue.pop(0)
        if curr in visited or curr == target_concept_id:
            continue
        visited.add(curr)
        transitive_prereqs.append(curr)
        for parent in prereq_graph.get(curr, []):
            if parent not in visited:
                queue.append(parent)

    ref_now = now or (clock.now() if clock is not None else datetime.now(UTC))
    flagged: list[dict[str, Any]] = []

    for pid in transitive_prereqs:
        m_data = user_masteries.get(pid)
        if m_data is None:
            flagged.append(
                {
                    "concept_id": pid,
                    "reason": "weak",
                    "p_known": 0.2,
                    "details": "Prerequisite concept has never been attempted.",
                }
            )
            continue

        p_val = float(m_data.get("p_known", 0.2))
        updated_at: datetime | None = m_data.get("updated_at")

        if p_val < weak_threshold:
            flagged.append(
                {
                    "concept_id": pid,
                    "reason": "weak",
                    "p_known": p_val,
                    "details": (
                        f"Mastery probability ({p_val:.2f}) is below threshold ({weak_threshold})."
                    ),
                }
            )
        elif updated_at is not None:
            # Check staleness
            delta_days = (ref_now - updated_at).days
            if delta_days > stale_threshold_days:
                flagged.append(
                    {
                        "concept_id": pid,
                        "reason": "stale",
                        "p_known": p_val,
                        "details": (
                            f"Mastery not exercised in {delta_days} days "
                            f"(threshold: {stale_threshold_days})."
                        ),
                    }
                )

    return flagged
