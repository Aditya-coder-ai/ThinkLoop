"""Unit tests for content YAML Pydantic schemas."""

import pytest
from pydantic import ValidationError


def test_valid_topic_schema() -> None:
    from app.content.schemas import TopicSchema

    data = {
        "schema_version": 1,
        "domain": "physics",
        "topic": "mechanics",
        "title": "Classical Newtonian Mechanics",
    }
    topic = TopicSchema.model_validate(data)
    assert topic.schema_version == 1
    assert topic.domain == "physics"
    assert topic.topic == "mechanics"
    assert topic.title == "Classical Newtonian Mechanics"


def test_topic_unknown_field_rejected() -> None:
    from app.content.schemas import TopicSchema

    data = {
        "schema_version": 1,
        "domain": "physics",
        "topic": "mechanics",
        "title": "Classical Newtonian Mechanics",
        "extra_field": "forbidden",
    }
    with pytest.raises(ValidationError):
        TopicSchema.model_validate(data)


def test_valid_concept_schema() -> None:
    from app.content.schemas import ConceptSchema

    data = {
        "id": "newtons_first_law",
        "title": "Newton's First Law",
        "description": (
            "An object remains at rest or in uniform motion "
            "unless acted upon by a net external force."
        ),
        "prerequisites": ["vectors", "inertia"],
        "difficulty": 3,
    }
    concept = ConceptSchema.model_validate(data)
    assert concept.id == "newtons_first_law"
    assert concept.difficulty == 3
    assert len(concept.prerequisites) == 2


def test_concept_bad_id_format_rejected() -> None:
    from app.content.schemas import ConceptSchema

    data = {
        "id": "Bad-ID With Spaces!",
        "title": "Bad Concept",
        "description": (
            "An object remains at rest or in uniform motion "
            "unless acted upon by a net external force."
        ),
        "prerequisites": [],
        "difficulty": 3,
    }
    with pytest.raises(ValidationError):
        ConceptSchema.model_validate(data)


def test_concept_difficulty_out_of_range_rejected() -> None:
    from app.content.schemas import ConceptSchema

    base = {
        "id": "valid_id",
        "title": "Valid Concept",
        "description": (
            "This is a sufficiently long description that satisfies the forty character minimum."
        ),
        "prerequisites": [],
    }
    with pytest.raises(ValidationError):
        ConceptSchema.model_validate({**base, "difficulty": 0})
    with pytest.raises(ValidationError):
        ConceptSchema.model_validate({**base, "difficulty": 6})


def test_concept_short_description_rejected() -> None:
    from app.content.schemas import ConceptSchema

    data = {
        "id": "valid_id",
        "title": "Valid Concept",
        "description": "Too short",
        "prerequisites": [],
        "difficulty": 2,
    }
    with pytest.raises(ValidationError):
        ConceptSchema.model_validate(data)


def test_valid_misconception_schema() -> None:
    from app.content.schemas import MisconceptionSchema

    data = {
        "id": "heavier_falls_faster",
        "concept_id": "gravity_free_fall",
        "statement": "Heavier objects fall faster than lighter objects in a vacuum.",
        "correct_idea": (
            "All objects in free fall experience the same gravitational acceleration."
        ),
        "conflict_prompt": (
            "Predict whether a 10kg iron ball and a 1kg wooden ball hit at the same time."
        ),
        "example_utterances": [
            "Heavy things drop faster because gravity pulls harder on them",
            "A bowling ball falls way faster than an apple",
            "Weight determines how quickly an object accelerates downward",
        ],
        "evidence": "Halloun & Hestenes (1985) Mechanics Diagnostic Test",
    }
    misc = MisconceptionSchema.model_validate(data)
    assert misc.id == "heavier_falls_faster"
    assert misc.concept_id == "gravity_free_fall"
    assert len(misc.example_utterances) == 3


def test_misconception_less_than_three_utterances_rejected() -> None:
    from app.content.schemas import MisconceptionSchema

    data = {
        "id": "heavier_falls_faster",
        "concept_id": "gravity_free_fall",
        "statement": "Heavier objects fall faster.",
        "correct_idea": "All objects accelerate at g.",
        "conflict_prompt": "What happens in a vacuum tube?",
        "example_utterances": [
            "Heavy things drop faster",
        ],
    }
    with pytest.raises(ValidationError):
        MisconceptionSchema.model_validate(data)


def test_valid_problem_schemas() -> None:
    from app.content.schemas import ProblemSchema

    # Numeric
    p1 = ProblemSchema.model_validate(
        {
            "id": "prob_numeric_1",
            "concept_id": "newtons_second_law",
            "statement": "Calculate the force required to accelerate a 5 kg block at 3 m/s^2.",
            "difficulty": 2,
            "answer_spec": {
                "kind": "numeric",
                "numeric": {"value": 15.0, "unit": "N", "tolerance": 0.05},
            },
        }
    )
    assert p1.answer_spec.kind == "numeric"
    assert p1.answer_spec.numeric is not None
    assert p1.answer_spec.numeric.value == 15.0

    # Symbolic
    p2 = ProblemSchema.model_validate(
        {
            "id": "prob_symbolic_1",
            "concept_id": "newtons_second_law",
            "statement": "Express acceleration 'a' in terms of net force 'F' and mass 'm'.",
            "difficulty": 3,
            "answer_spec": {
                "kind": "symbolic",
                "symbolic": {"expression": "F/m"},
            },
        }
    )
    assert p2.answer_spec.kind == "symbolic"
    assert p2.answer_spec.symbolic is not None
    assert p2.answer_spec.symbolic.expression == "F/m"

    # Multiple Choice
    p3 = ProblemSchema.model_validate(
        {
            "id": "prob_mc_1",
            "concept_id": "newtons_first_law",
            "statement": (
                "What net force is required to keep an object moving at constant velocity in space?"
            ),
            "difficulty": 1,
            "answer_spec": {
                "kind": "multiple_choice",
                "multiple_choice": {
                    "options": [
                        "Zero net force",
                        "Constant force equal to mass",
                        "Increasing force",
                    ],
                    "correct_index": 0,
                },
            },
        }
    )
    assert p3.answer_spec.kind == "multiple_choice"
    assert p3.answer_spec.multiple_choice is not None
    assert p3.answer_spec.multiple_choice.correct_index == 0


def test_problem_multiple_choice_out_of_range_rejected() -> None:
    from app.content.schemas import ProblemSchema

    with pytest.raises(ValidationError):
        ProblemSchema.model_validate(
            {
                "id": "prob_mc_bad",
                "concept_id": "c1",
                "statement": "Test question?",
                "difficulty": 2,
                "answer_spec": {
                    "kind": "multiple_choice",
                    "multiple_choice": {
                        "options": ["Option A", "Option B"],
                        "correct_index": 5,
                    },
                },
            }
        )
