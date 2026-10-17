"""Unit tests for content validator rules."""

from pathlib import Path


def test_validator_detects_duplicate_id(tmp_path: Path) -> None:
    from app.content.validator import ContentValidator

    topic_dir = tmp_path / "physics" / "mechanics"
    topic_dir.mkdir(parents=True)

    (topic_dir / "topic.yaml").write_text(
        "schema_version: 1\ndomain: physics\ntopic: mechanics\ntitle: Mechanics\n"
    )
    (topic_dir / "concepts.yaml").write_text(
        "- id: duplicate_id\n"
        "  title: Concept One\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: []\n"
        "  difficulty: 1\n"
        "- id: duplicate_id\n"
        "  title: Concept Two\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: []\n"
        "  difficulty: 2\n"
    )
    (topic_dir / "misconceptions.yaml").write_text("[]\n")
    (topic_dir / "problems.yaml").write_text("[]\n")

    validator = ContentValidator(content_root=tmp_path)
    result = validator.validate()

    assert not result.is_valid
    assert any("duplicate" in err.message.lower() for err in result.errors)


def test_validator_detects_unknown_concept_reference(tmp_path: Path) -> None:
    from app.content.validator import ContentValidator

    topic_dir = tmp_path / "physics" / "mechanics"
    topic_dir.mkdir(parents=True)

    (topic_dir / "topic.yaml").write_text(
        "schema_version: 1\ndomain: physics\ntopic: mechanics\ntitle: Mechanics\n"
    )
    (topic_dir / "concepts.yaml").write_text("[]\n")
    (topic_dir / "misconceptions.yaml").write_text(
        "- id: m1\n"
        "  concept_id: non_existent_concept\n"
        "  statement: Statement text\n"
        "  correct_idea: Correct\n"
        "  conflict_prompt: Predict\n"
        "  example_utterances: ['u1', 'u2', 'u3']\n"
    )
    (topic_dir / "problems.yaml").write_text("[]\n")

    validator = ContentValidator(content_root=tmp_path)
    result = validator.validate()

    assert not result.is_valid
    assert any("non_existent_concept" in err.message for err in result.errors)


def test_validator_detects_three_node_cycle(tmp_path: Path) -> None:
    from app.content.validator import ContentValidator

    topic_dir = tmp_path / "physics" / "mechanics"
    topic_dir.mkdir(parents=True)

    (topic_dir / "topic.yaml").write_text(
        "schema_version: 1\ndomain: physics\ntopic: mechanics\ntitle: Mechanics\n"
    )
    # 3-node cycle: a -> b -> c -> a
    (topic_dir / "concepts.yaml").write_text(
        "- id: a\n"
        "  title: Concept A\n"
        "  description: A long description exceeding forty characters for concept A.\n"
        "  prerequisites: [c]\n"
        "  difficulty: 1\n"
        "- id: b\n"
        "  title: Concept B\n"
        "  description: A long description exceeding forty characters for concept B.\n"
        "  prerequisites: [a]\n"
        "  difficulty: 1\n"
        "- id: c\n"
        "  title: Concept C\n"
        "  description: A long description exceeding forty characters for concept C.\n"
        "  prerequisites: [b]\n"
        "  difficulty: 1\n"
    )
    (topic_dir / "misconceptions.yaml").write_text("[]\n")
    (topic_dir / "problems.yaml").write_text("[]\n")

    validator = ContentValidator(content_root=tmp_path)
    result = validator.validate()

    assert not result.is_valid
    cycle_errors = [e for e in result.errors if "cycle" in e.message.lower()]
    assert len(cycle_errors) > 0
    # Error message must contain cycle path components
    cycle_msg = cycle_errors[0].message
    assert "a" in cycle_msg and "b" in cycle_msg and "c" in cycle_msg


def test_validator_detects_self_prerequisite(tmp_path: Path) -> None:
    from app.content.validator import ContentValidator

    topic_dir = tmp_path / "physics" / "mechanics"
    topic_dir.mkdir(parents=True)

    (topic_dir / "topic.yaml").write_text(
        "schema_version: 1\ndomain: physics\ntopic: mechanics\ntitle: Mechanics\n"
    )
    (topic_dir / "concepts.yaml").write_text(
        "- id: self_ref\n"
        "  title: Self Concept\n"
        "  description: A long description exceeding forty characters for concept.\n"
        "  prerequisites: [self_ref]\n"
        "  difficulty: 1\n"
    )
    (topic_dir / "misconceptions.yaml").write_text("[]\n")
    (topic_dir / "problems.yaml").write_text("[]\n")

    validator = ContentValidator(content_root=tmp_path)
    result = validator.validate()

    assert not result.is_valid
    assert any(
        "self-prerequisite" in err.message.lower() or "self_ref" in err.message
        for err in result.errors
    )


def test_validator_rejects_bad_sympy_expression(tmp_path: Path) -> None:
    from app.content.validator import ContentValidator

    topic_dir = tmp_path / "physics" / "mechanics"
    topic_dir.mkdir(parents=True)

    (topic_dir / "topic.yaml").write_text(
        "schema_version: 1\ndomain: physics\ntopic: mechanics\ntitle: Mechanics\n"
    )
    (topic_dir / "concepts.yaml").write_text(
        "- id: c1\n"
        "  title: Concept One\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: []\n"
        "  difficulty: 1\n"
    )
    (topic_dir / "misconceptions.yaml").write_text("[]\n")
    (topic_dir / "problems.yaml").write_text(
        "- id: p1\n"
        "  concept_id: c1\n"
        "  statement: Solve for a\n"
        "  difficulty: 2\n"
        "  answer_spec:\n"
        "    kind: symbolic\n"
        "    symbolic:\n"
        "      expression: 'F / * m'\n"
    )

    validator = ContentValidator(content_root=tmp_path)
    result = validator.validate()

    assert not result.is_valid
    assert any(
        "symbolic" in err.message.lower() or "sympy" in err.message.lower() for err in result.errors
    )


def test_validator_reports_all_errors_in_one_run(tmp_path: Path) -> None:
    from app.content.validator import ContentValidator

    topic_dir = tmp_path / "physics" / "mechanics"
    topic_dir.mkdir(parents=True)

    (topic_dir / "topic.yaml").write_text(
        "schema_version: 1\ndomain: physics\ntopic: mechanics\ntitle: Mechanics\n"
    )
    # File with 5 mistakes:
    # 1. Duplicate concept id c1
    # 2. Concept with invalid id format "Bad Id"
    # 3. Concept with missing prereq "ghost_prereq"
    # 4. Misconception with unknown concept "ghost_concept"
    # 5. Problem with invalid sympy expression "F ** / 2"
    (topic_dir / "concepts.yaml").write_text(
        "- id: c1\n"
        "  title: Concept One\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: []\n"
        "  difficulty: 1\n"
        "- id: c1\n"
        "  title: Concept One Dup\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: []\n"
        "  difficulty: 1\n"
        "- id: Bad Id\n"
        "  title: Bad\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: []\n"
        "  difficulty: 1\n"
        "- id: c3\n"
        "  title: Concept Three\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: [ghost_prereq]\n"
        "  difficulty: 1\n"
    )
    (topic_dir / "misconceptions.yaml").write_text(
        "- id: m1\n"
        "  concept_id: ghost_concept\n"
        "  statement: Statement text\n"
        "  correct_idea: Correct\n"
        "  conflict_prompt: Predict\n"
        "  example_utterances: ['u1', 'u2', 'u3']\n"
    )
    (topic_dir / "problems.yaml").write_text(
        "- id: p1\n"
        "  concept_id: c1\n"
        "  statement: Statement text\n"
        "  difficulty: 2\n"
        "  answer_spec:\n"
        "    kind: symbolic\n"
        "    symbolic:\n"
        "      expression: 'F ** / 2'\n"
    )

    validator = ContentValidator(content_root=tmp_path)
    result = validator.validate()

    assert not result.is_valid
    # Must report all errors together, not bail on first error
    assert len(result.errors) >= 5


def test_validator_warnings_vs_strict_mode(tmp_path: Path) -> None:
    from app.content.validator import ContentValidator

    topic_dir = tmp_path / "physics" / "mechanics"
    topic_dir.mkdir(parents=True)

    (topic_dir / "topic.yaml").write_text(
        "schema_version: 1\ndomain: physics\ntopic: mechanics\ntitle: Mechanics\n"
    )
    # 2 concepts: c1 -> c2, but c3 is completely orphaned (no incoming or outgoing edges)
    # Also c2 has zero misconceptions and zero problems
    (topic_dir / "concepts.yaml").write_text(
        "- id: c1\n"
        "  title: Concept One\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: []\n"
        "  difficulty: 1\n"
        "- id: c2\n"
        "  title: Concept Two\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: [c1]\n"
        "  difficulty: 2\n"
        "- id: orphan_c3\n"
        "  title: Concept Three Orphan\n"
        "  description: An extensive description with more than forty characters.\n"
        "  prerequisites: []\n"
        "  difficulty: 3\n"
    )
    (topic_dir / "misconceptions.yaml").write_text(
        "- id: m1\n"
        "  concept_id: c1\n"
        "  statement: Statement text\n"
        "  correct_idea: Correct\n"
        "  conflict_prompt: Predict\n"
        "  example_utterances: ['u1 duplicate', 'u1 duplicate', 'u3']\n"
    )
    (topic_dir / "problems.yaml").write_text(
        "- id: p1\n"
        "  concept_id: c1\n"
        "  statement: Statement text\n"
        "  difficulty: 2\n"
        "  answer_spec:\n"
        "    kind: numeric\n"
        "    numeric:\n"
        "      value: 10.0\n"
        "      unit: 'm/s'\n"
        "      tolerance: 0.1\n"
    )

    validator = ContentValidator(content_root=tmp_path)
    result = validator.validate()

    # In non-strict mode, warnings do not make result invalid if errors == 0
    assert len(result.errors) == 0
    assert len(result.warnings) > 0
    assert result.has_warnings
    assert result.is_valid  # valid in standard mode

    # In strict mode, warnings count as failures
    assert not result.is_valid_strict
