from datetime import UTC, datetime, timedelta

import pytest

from app.core.learner_model import (
    BKTParams,
    bkt_update,
    classify_mastery_state,
    find_weak_or_stale_prerequisites,
)


def test_bkt_update_known_numeric_values() -> None:
    """Verify BKT mathematical update against hand-calculated analytical values."""
    params = BKTParams(p_learn=0.15, p_slip=0.1, p_guess=0.2)

    # Correct observation from prior 0.5
    # P(L|obs=1) = (0.5 * 0.9) / (0.5 * 0.9 + 0.5 * 0.2) = 0.45 / 0.55 = 0.8181818
    # P(L) = 0.8181818 + (1 - 0.8181818) * 0.15 = 0.8454545
    p_next_correct = bkt_update(p_known=0.5, correct=True, params=params)
    assert pytest.approx(p_next_correct, rel=1e-4) == 0.84545

    # Incorrect observation from prior 0.5
    # P(L|obs=0) = (0.5 * 0.1) / (0.5 * 0.1 + 0.5 * 0.8) = 0.05 / 0.45 = 0.1111111
    # P(L) = 0.1111111 + (1 - 0.1111111) * 0.15 = 0.2444444
    p_next_incorrect = bkt_update(p_known=0.5, correct=False, params=params)
    assert pytest.approx(p_next_incorrect, rel=1e-4) == 0.24444


def test_bkt_monotonicity() -> None:
    """BKT probability must increase monotonically on correct and decrease on incorrect."""
    p_initial = 0.3
    p_correct = bkt_update(p_known=p_initial, correct=True)
    p_correct_again = bkt_update(p_known=p_correct, correct=True)
    assert p_correct > p_initial
    assert p_correct_again > p_correct

    p_incorrect = bkt_update(p_known=p_initial, correct=False)
    p_incorrect_again = bkt_update(p_known=p_incorrect, correct=False)
    assert p_incorrect < p_initial
    assert p_incorrect_again < p_incorrect


def test_bkt_clamping_bounds() -> None:
    """BKT probabilities must strictly respect [0.001, 0.999] boundary conditions."""
    # Repeated incorrect updates must not dip below 0.001
    p = 0.1
    for _ in range(50):
        p = bkt_update(p_known=p, correct=False)
    assert p >= 0.001

    # Repeated correct updates must not exceed 0.999
    p = 0.9
    for _ in range(50):
        p = bkt_update(p_known=p, correct=True)
    assert p <= 0.999


def test_classify_mastery_state() -> None:
    """Mastery state classifies into unseen, learning, or mastered."""
    assert classify_mastery_state(p_known=0.1, attempts=0) == "unseen"
    assert classify_mastery_state(p_known=0.2, attempts=1) == "unseen"
    assert classify_mastery_state(p_known=0.5, attempts=2) == "learning"
    assert classify_mastery_state(p_known=0.85, attempts=4) == "mastered"
    assert classify_mastery_state(p_known=0.99, attempts=5) == "mastered"


def test_find_weak_or_stale_prerequisites() -> None:
    """Prerequisite awareness correctly flags weak (<0.4) or stale prerequisites."""
    # Graph: c1 -> c2 -> c3
    prereq_graph = {
        "c3": ["c2"],
        "c2": ["c1"],
        "c1": [],
    }

    now = datetime.now(UTC)
    user_masteries = {
        # c1 is weak (p=0.25)
        "c1": {
            "p_known": 0.25,
            "updated_at": now - timedelta(days=2),
        },
        # c2 is mastered (p=0.90) but stale (updated 40 days ago)
        "c2": {
            "p_known": 0.90,
            "updated_at": now - timedelta(days=40),
        },
    }

    flags = find_weak_or_stale_prerequisites(
        target_concept_id="c3",
        prereq_graph=prereq_graph,
        user_masteries=user_masteries,
        stale_threshold_days=30,
        weak_threshold=0.4,
    )

    assert len(flags) == 2
    flag_dict = {f["concept_id"]: f["reason"] for f in flags}
    assert flag_dict["c1"] == "weak"
    assert flag_dict["c2"] == "stale"
