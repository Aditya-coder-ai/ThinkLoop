"""Content validation engine for Thinkloop YAML curriculum.

Performs schema validation, cross-file referential integrity, and graph DAG checks.
Reports all errors at once.
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
import sympy
import yaml
from pydantic import ValidationError

from app.content.schemas import (
    ConceptSchema,
    MisconceptionSchema,
    ProblemSchema,
    TopicSchema,
)


@dataclass(frozen=True)
class ValidationErrorItem:
    """Detailed error reported during validation."""

    file_path: str
    item_id: str | None
    message: str


@dataclass(frozen=True)
class ValidationWarningItem:
    """Warning reported during validation (fails in --strict mode)."""

    file_path: str
    item_id: str | None
    message: str


@dataclass
class ValidationResult:
    """Comprehensive validation outcome holding all errors and warnings."""

    errors: list[ValidationErrorItem] = field(default_factory=list)
    warnings: list[ValidationWarningItem] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if there are zero errors (warnings allowed in standard mode)."""
        return len(self.errors) == 0

    @property
    def is_valid_strict(self) -> bool:
        """True only if there are zero errors AND zero warnings."""
        return len(self.errors) == 0 and len(self.warnings) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


class ContentValidator:
    """Validates all topic directories under content_root."""

    def __init__(self, content_root: Path | str) -> None:
        self.content_root = Path(content_root)

    def validate(self) -> ValidationResult:
        """Execute full schema, cross-reference, and graph validation."""
        result = ValidationResult()

        if not self.content_root.exists():
            result.errors.append(
                ValidationErrorItem(
                    file_path=str(self.content_root),
                    item_id=None,
                    message=f"Content root directory does not exist: {self.content_root}",
                )
            )
            return result

        # 1. Discover all topic directories (directories containing topic.yaml)
        topic_dirs: list[Path] = []
        for path in self.content_root.rglob("topic.yaml"):
            topic_dirs.append(path.parent)

        if not topic_dirs:
            result.warnings.append(
                ValidationWarningItem(
                    file_path=str(self.content_root),
                    item_id=None,
                    message="No topic directories containing 'topic.yaml' found.",
                )
            )
            return result

        # Global registries for uniqueness & cross-topic referential checks
        all_concepts: dict[str, tuple[Path, ConceptSchema]] = {}
        all_misconceptions: dict[str, tuple[Path, MisconceptionSchema]] = {}
        all_problems: dict[str, tuple[Path, ProblemSchema]] = {}

        # Collect raw parsed objects by topic
        topic_concepts: dict[Path, list[ConceptSchema]] = {}
        topic_misconceptions: dict[Path, list[MisconceptionSchema]] = {}
        topic_problems: dict[Path, list[ProblemSchema]] = {}

        for topic_dir in topic_dirs:
            # Validate topic.yaml
            self._validate_topic_file(topic_dir, result)

            # Validate concepts.yaml
            c_list = self._validate_concepts_file(topic_dir, result, all_concepts)
            topic_concepts[topic_dir] = c_list

            # Validate misconceptions.yaml
            m_list = self._validate_misconceptions_file(topic_dir, result, all_misconceptions)
            topic_misconceptions[topic_dir] = m_list

            # Validate problems.yaml
            p_list = self._validate_problems_file(topic_dir, result, all_problems)
            topic_problems[topic_dir] = p_list

        # Cross-file referential integrity & graph checks
        self._validate_cross_references(
            result=result,
            all_concepts=all_concepts,
            all_misconceptions=all_misconceptions,
            all_problems=all_problems,
        )

        # Graph DAG checks per topic and globally
        self._validate_graph(result=result, all_concepts=all_concepts)

        # Content quality and orphan checks
        self._validate_content_quality(
            result=result,
            topic_concepts=topic_concepts,
            topic_misconceptions=topic_misconceptions,
            topic_problems=topic_problems,
        )

        return result

    def load_all(self) -> dict[str, Any]:
        """Discover and load all valid curriculum schemas under content_root."""
        topics: list[TopicSchema] = []
        concepts: list[ConceptSchema] = []
        misconceptions: list[MisconceptionSchema] = []
        problems: list[ProblemSchema] = []

        for path in self.content_root.rglob("topic.yaml"):
            topic_dir = path.parent
            with open(path, encoding="utf-8") as f:
                raw_topic = yaml.safe_load(f)
                if raw_topic:
                    topics.append(TopicSchema.model_validate(raw_topic))

            c_file = topic_dir / "concepts.yaml"
            if c_file.exists():
                with open(c_file, encoding="utf-8") as f:
                    raw_c = yaml.safe_load(f) or []
                    for item in raw_c:
                        concepts.append(ConceptSchema.model_validate(item))

            m_file = topic_dir / "misconceptions.yaml"
            if m_file.exists():
                with open(m_file, encoding="utf-8") as f:
                    raw_m = yaml.safe_load(f) or []
                    for item in raw_m:
                        misconceptions.append(MisconceptionSchema.model_validate(item))

            p_file = topic_dir / "problems.yaml"
            if p_file.exists():
                with open(p_file, encoding="utf-8") as f:
                    raw_p = yaml.safe_load(f) or []
                    for item in raw_p:
                        problems.append(ProblemSchema.model_validate(item))

        return {
            "topics": topics,
            "concepts": concepts,
            "misconceptions": misconceptions,
            "problems": problems,
        }

    def _safe_load_yaml(self, file_path: Path, result: ValidationResult) -> Any:
        if not file_path.exists():
            result.errors.append(
                ValidationErrorItem(
                    file_path=str(file_path),
                    item_id=None,
                    message=f"Required content file is missing: {file_path.name}",
                )
            )
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as exc:
            result.errors.append(
                ValidationErrorItem(
                    file_path=str(file_path),
                    item_id=None,
                    message=f"YAML syntax error: {exc}",
                )
            )
            return None

    def _validate_topic_file(self, topic_dir: Path, result: ValidationResult) -> None:
        file_path = topic_dir / "topic.yaml"
        raw_data = self._safe_load_yaml(file_path, result)
        if raw_data is None:
            return

        try:
            TopicSchema.model_validate(raw_data)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"])
                result.errors.append(
                    ValidationErrorItem(
                        file_path=str(file_path),
                        item_id=loc,
                        message=f"{loc}: {err['msg']}",
                    )
                )

    def _validate_concepts_file(
        self,
        topic_dir: Path,
        result: ValidationResult,
        all_concepts: dict[str, tuple[Path, ConceptSchema]],
    ) -> list[ConceptSchema]:
        file_path = topic_dir / "concepts.yaml"
        raw_data = self._safe_load_yaml(file_path, result)
        if raw_data is None:
            return []

        if not isinstance(raw_data, list):
            result.errors.append(
                ValidationErrorItem(
                    file_path=str(file_path),
                    item_id=None,
                    message="concepts.yaml must contain a top-level YAML list",
                )
            )
            return []

        concepts: list[ConceptSchema] = []
        for index, item in enumerate(raw_data):
            item_id = item.get("id") if isinstance(item, dict) else str(index)
            try:
                concept = ConceptSchema.model_validate(item)
                if concept.id in all_concepts:
                    orig_path, _ = all_concepts[concept.id]
                    result.errors.append(
                        ValidationErrorItem(
                            file_path=str(file_path),
                            item_id=concept.id,
                            message=(
                                f"Duplicate concept id '{concept.id}' "
                                f"already declared in {orig_path}"
                            ),
                        )
                    )
                else:
                    all_concepts[concept.id] = (file_path, concept)
                concepts.append(concept)
            except ValidationError as exc:
                for err in exc.errors():
                    field_loc = ".".join(str(p) for p in err["loc"])
                    result.errors.append(
                        ValidationErrorItem(
                            file_path=str(file_path),
                            item_id=str(item_id),
                            message=f"Field '{field_loc}': {err['msg']}",
                        )
                    )
        return concepts

    def _validate_misconceptions_file(
        self,
        topic_dir: Path,
        result: ValidationResult,
        all_misconceptions: dict[str, tuple[Path, MisconceptionSchema]],
    ) -> list[MisconceptionSchema]:
        file_path = topic_dir / "misconceptions.yaml"
        raw_data = self._safe_load_yaml(file_path, result)
        if raw_data is None:
            return []

        if not isinstance(raw_data, list):
            result.errors.append(
                ValidationErrorItem(
                    file_path=str(file_path),
                    item_id=None,
                    message="misconceptions.yaml must contain a top-level YAML list",
                )
            )
            return []

        misconceptions: list[MisconceptionSchema] = []
        for index, item in enumerate(raw_data):
            item_id = item.get("id") if isinstance(item, dict) else str(index)
            try:
                misc = MisconceptionSchema.model_validate(item)
                if misc.id in all_misconceptions:
                    orig_path, _ = all_misconceptions[misc.id]
                    result.errors.append(
                        ValidationErrorItem(
                            file_path=str(file_path),
                            item_id=misc.id,
                            message=(
                                f"Duplicate misconception id '{misc.id}' "
                                f"already declared in {orig_path}"
                            ),
                        )
                    )
                else:
                    all_misconceptions[misc.id] = (file_path, misc)
                misconceptions.append(misc)
            except ValidationError as exc:
                for err in exc.errors():
                    field_loc = ".".join(str(p) for p in err["loc"])
                    result.errors.append(
                        ValidationErrorItem(
                            file_path=str(file_path),
                            item_id=str(item_id),
                            message=f"Field '{field_loc}': {err['msg']}",
                        )
                    )
        return misconceptions

    def _validate_problems_file(
        self,
        topic_dir: Path,
        result: ValidationResult,
        all_problems: dict[str, tuple[Path, ProblemSchema]],
    ) -> list[ProblemSchema]:
        file_path = topic_dir / "problems.yaml"
        raw_data = self._safe_load_yaml(file_path, result)
        if raw_data is None:
            return []

        if not isinstance(raw_data, list):
            result.errors.append(
                ValidationErrorItem(
                    file_path=str(file_path),
                    item_id=None,
                    message="problems.yaml must contain a top-level YAML list",
                )
            )
            return []

        problems: list[ProblemSchema] = []
        for index, item in enumerate(raw_data):
            item_id = item.get("id") if isinstance(item, dict) else str(index)
            try:
                problem = ProblemSchema.model_validate(item)
                if problem.id in all_problems:
                    orig_path, _ = all_problems[problem.id]
                    result.errors.append(
                        ValidationErrorItem(
                            file_path=str(file_path),
                            item_id=problem.id,
                            message=(
                                f"Duplicate problem id '{problem.id}' "
                                f"already declared in {orig_path}"
                            ),
                        )
                    )
                else:
                    all_problems[problem.id] = (file_path, problem)

                # Validate symbolic expression with SymPy
                if problem.answer_spec.kind == "symbolic" and problem.answer_spec.symbolic:
                    expr_str = problem.answer_spec.symbolic.expression
                    try:
                        sympy.sympify(expr_str)
                    except Exception as sym_exc:
                        result.errors.append(
                            ValidationErrorItem(
                                file_path=str(file_path),
                                item_id=problem.id,
                                message=(
                                    f"Symbolic answer expression '{expr_str}' "
                                    f"could not be parsed by sympy: {sym_exc}"
                                ),
                            )
                        )

                problems.append(problem)
            except ValidationError as exc:
                for err in exc.errors():
                    field_loc = ".".join(str(p) for p in err["loc"])
                    result.errors.append(
                        ValidationErrorItem(
                            file_path=str(file_path),
                            item_id=str(item_id),
                            message=f"Field '{field_loc}': {err['msg']}",
                        )
                    )
        return problems

    def _validate_cross_references(
        self,
        result: ValidationResult,
        all_concepts: dict[str, tuple[Path, ConceptSchema]],
        all_misconceptions: dict[str, tuple[Path, MisconceptionSchema]],
        all_problems: dict[str, tuple[Path, ProblemSchema]],
    ) -> None:
        # Check unknown concept references in prerequisites
        for c_id, (path, concept) in all_concepts.items():
            for prereq_id in concept.prerequisites:
                if prereq_id == c_id:
                    result.errors.append(
                        ValidationErrorItem(
                            file_path=str(path),
                            item_id=c_id,
                            message=f"Concept '{c_id}' has self-prerequisite on itself.",
                        )
                    )
                elif prereq_id not in all_concepts:
                    result.errors.append(
                        ValidationErrorItem(
                            file_path=str(path),
                            item_id=c_id,
                            message=(
                                f"Concept '{c_id}' references unknown prerequisite '{prereq_id}'."
                            ),
                        )
                    )

        # Check unknown concept references in misconceptions
        for m_id, (path, misc) in all_misconceptions.items():
            if misc.concept_id not in all_concepts:
                result.errors.append(
                    ValidationErrorItem(
                        file_path=str(path),
                        item_id=m_id,
                        message=(
                            f"Misconception '{m_id}' references unknown concept_id "
                            f"'{misc.concept_id}'."
                        ),
                    )
                )

        # Check unknown concept references in problems
        for p_id, (path, prob) in all_problems.items():
            if prob.concept_id not in all_concepts:
                result.errors.append(
                    ValidationErrorItem(
                        file_path=str(path),
                        item_id=p_id,
                        message=(
                            f"Problem '{p_id}' references unknown concept_id '{prob.concept_id}'."
                        ),
                    )
                )

    def _validate_graph(
        self,
        result: ValidationResult,
        all_concepts: dict[str, tuple[Path, ConceptSchema]],
    ) -> None:
        graph = nx.DiGraph()
        for c_id in all_concepts:
            graph.add_node(c_id)

        for c_id, (_, concept) in all_concepts.items():
            for prereq_id in concept.prerequisites:
                if prereq_id in all_concepts and prereq_id != c_id:
                    # Edge from prerequisite to dependent concept (prereq -> c_id)
                    graph.add_edge(prereq_id, c_id)

        # Check for cycles
        if not nx.is_directed_acyclic_graph(graph):
            try:
                cycles = list(nx.simple_cycles(graph))
                for cycle in cycles:
                    cycle_path = " -> ".join(cycle + [cycle[0]])
                    result.errors.append(
                        ValidationErrorItem(
                            file_path=str(self.content_root),
                            item_id=None,
                            message=f"Prerequisite cycle detected in concept graph: {cycle_path}",
                        )
                    )
            except Exception as exc:
                result.errors.append(
                    ValidationErrorItem(
                        file_path=str(self.content_root),
                        item_id=None,
                        message=f"Graph is not a DAG (contains cycles): {exc}",
                    )
                )

    def _validate_content_quality(
        self,
        result: ValidationResult,
        topic_concepts: dict[Path, list[ConceptSchema]],
        topic_misconceptions: dict[Path, list[MisconceptionSchema]],
        topic_problems: dict[Path, list[ProblemSchema]],
    ) -> None:
        # Check duplicate example utterances in each misconception (warning)
        for topic_dir, m_list in topic_misconceptions.items():
            file_path = topic_dir / "misconceptions.yaml"
            for misc in m_list:
                counts = Counter(misc.example_utterances)
                dups = [utt for utt, c in counts.items() if c > 1]
                if dups:
                    result.warnings.append(
                        ValidationWarningItem(
                            file_path=str(file_path),
                            item_id=misc.id,
                            message=(
                                f"Misconception '{misc.id}' contains duplicate example "
                                f"utterances: {dups}"
                            ),
                        )
                    )

        # Check orphan concepts and concept coverage (warning)
        for topic_dir, c_list in topic_concepts.items():
            file_path = topic_dir / "concepts.yaml"
            m_list = topic_misconceptions.get(topic_dir, [])
            p_list = topic_problems.get(topic_dir, [])

            covered_misconception_concepts = {m.concept_id for m in m_list}
            covered_problem_concepts = {p.concept_id for p in p_list}

            # Graph for this topic to check orphans
            if len(c_list) > 1:
                topic_graph = nx.DiGraph()
                for c in c_list:
                    topic_graph.add_node(c.id)
                for c in c_list:
                    for prereq in c.prerequisites:
                        if prereq in topic_graph:
                            topic_graph.add_edge(prereq, c.id)

                for c in c_list:
                    in_deg = topic_graph.in_degree(c.id)
                    out_deg = topic_graph.out_degree(c.id)
                    if in_deg == 0 and out_deg == 0:
                        result.warnings.append(
                            ValidationWarningItem(
                                file_path=str(file_path),
                                item_id=c.id,
                                message=(
                                    f"Orphan concept '{c.id}' has no prerequisite or "
                                    f"dependent edges in topic with {len(c_list)} concepts"
                                ),
                            )
                        )

            # Check for zero misconceptions / problems
            for c in c_list:
                if c.id not in covered_misconception_concepts:
                    result.warnings.append(
                        ValidationWarningItem(
                            file_path=str(file_path),
                            item_id=c.id,
                            message=f"Concept '{c.id}' has zero associated misconceptions.",
                        )
                    )
                if c.id not in covered_problem_concepts:
                    result.warnings.append(
                        ValidationWarningItem(
                            file_path=str(file_path),
                            item_id=c.id,
                            message=f"Concept '{c.id}' has zero associated problems.",
                        )
                    )
