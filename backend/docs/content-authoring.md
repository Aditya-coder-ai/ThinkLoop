# Thinkloop Curriculum Content Authoring Guide

Welcome to the Thinkloop curriculum authoring guide. This document explains how educators, teachers, and curriculum designers can author, test, and maintain learning content (concepts, prerequisites, misconceptions, and problems) in Thinkloop.

---

## 1. Architecture & Core Philosophy

1. **Git & YAML is the Single Source of Truth**: All curriculum content lives in versioned YAML files in the Git repository. The database is a derived transactional cache of these files.
2. **Strict Validation Before Deployment**: Content cannot be synced or deployed until automated validation passes with zero errors.
3. **Learner Safety & Security**: The `answer_spec` (correct answers and numerical tolerances) is strictly kept on the server and is never exposed to students through the learner APIs.
4. **No Content is Lost**: If a concept or problem is removed from YAML, it is soft-deactivated (`is_active: false`) in the database so past learner mastery records are never broken.

---

## 2. Directory Structure

Curriculum content is organized by domain and topic:

```text
backend/content/
  └── <domain>/                # e.g., physics, math, chemistry
        └── <topic>/            # e.g., mechanics, thermodynamics, calculus
              ├── topic.yaml           # Topic metadata
              ├── concepts.yaml        # Core concepts and prerequisite edges
              ├── misconceptions.yaml  # Catalog of student misconceptions
              └── problems.yaml        # Practice and assessment problems
```

---

## 3. Authoring Files Step-by-Step

### 3.1. Topic Metadata (`topic.yaml`)
Every topic directory must have a `topic.yaml` file:

```yaml
schema_version: 1
domain: physics
topic: mechanics
title: "Classical Newtonian Mechanics"
```

- **`schema_version`**: Must be `1`.
- **`domain`**: Lowercase identifier (e.g., `physics`).
- **`topic`**: Lowercase snake_case identifier (e.g., `mechanics`).
- **`title`**: Human-readable name.

---

### 3.2. Concepts (`concepts.yaml`)
Concepts define the knowledge nodes and the prerequisite learning graph (Directed Acyclic Graph):

```yaml
- id: newtons_second_law
  title: "Newton's Second Law"
  description: "The net external force on an object equals the product of its mass and acceleration vector, mathematically expressed as F_net equals m times a."
  prerequisites:
    - newtons_first_law
  difficulty: 2
```

#### Rules:
- **`id`**: Lowercase snake_case (e.g. `newtons_second_law`). Must be globally unique across all topics.
- **`title`**: Descriptive title.
- **`description`**: Clear pedagogical description of at least **40 characters**.
- **`prerequisites`**: List of concept IDs that must be learned before this concept.
  - **No Cycles**: A concept cannot depend on itself, nor can prerequisites loop (e.g., A -> B -> C -> A is forbidden).
  - **No Orphans**: In any topic with more than one concept, every concept should have at least one incoming or outgoing prerequisite connection.
- **`difficulty`**: Integer rating from `1` (introductory) to `5` (advanced).

---

### 3.3. Misconceptions (`misconceptions.yaml`)
Misconceptions capture incorrect mental models identified in pedagogical research (such as Physics Education Research literature). Thinkloop uses these to guide Socratic interventions.

```yaml
- id: misc_motion_requires_force
  concept_id: newtons_first_law
  statement: "An object needs a continuous forward force acting on it to keep moving at a constant speed."
  correct_idea: "By Newton's first law, an object in motion continues with constant velocity unless a net external force opposes it; friction slows objects down on Earth."
  conflict_prompt: "Predict what will happen to a spacecraft drifting in deep space after its engines are completely turned off."
  example_utterances:
    - "Without an engine push, any moving object will naturally slow down to a stop in space."
    - "Continuous motion requires a continuing force."
    - "If you stop applying a force, the object stops moving immediately."
  evidence: "Halloun & Hestenes (1985), Common sense concepts about motion, American Journal of Physics"
```

#### Rules:
- **`concept_id`**: Must match an existing concept ID in `concepts.yaml`.
- **`statement`**: The erroneous belief expressed in the first person.
- **`correct_idea`**: The scientifically accurate understanding.
- **`conflict_prompt`**: A **prediction-style question** that encourages the student to confront the contradiction in their mental model.
- **`example_utterances`**: At least **3 realistic ways** real students phrase this misunderstanding.
- **`evidence`**: Optional citation or source note from educational research literature.
- **`# REVIEW` tag**: If you are uncertain about phrasing or physics boundaries, add a comment `# REVIEW: <reason>` for peer review.

---

### 3.4. Problems (`problems.yaml`)
Problems test learner understanding. Thinkloop supports three question formats: numeric, symbolic, and multiple choice.

#### Numeric Problem Example:
```yaml
- id: prob_newton_second_calc
  concept_id: newtons_second_law
  statement: "What net horizontal force in Newtons is required to accelerate a 12.0 kg sled at 2.5 m/s^2 across a frictionless frozen lake?"
  difficulty: 2
  answer_spec:
    kind: numeric
    numeric:
      value: 30.0
      unit: "N"
      tolerance: 0.01  # Acceptable relative tolerance (0.0 to 1.0)
```

#### Symbolic Problem Example:
```yaml
- id: prob_newton_second_formula
  concept_id: newtons_second_law
  statement: "Express the magnitude of acceleration 'a' of an object of mass 'm' subjected to net force 'F'."
  difficulty: 2
  answer_spec:
    kind: symbolic
    symbolic:
      expression: "F / m"  # Must parse with SymPy mathematical parser
```

#### Multiple Choice Problem Example:
```yaml
- id: prob_spacecraft_motion
  concept_id: newtons_first_law
  statement: "A spacecraft in deep space far from any star shuts down its engines. What happens to its speed?"
  difficulty: 1
  answer_spec:
    kind: multiple_choice
    multiple_choice:
      options:
        - "It will continue moving at the same speed in a straight line"
        - "It will gradually slow down to a complete stop"
        - "It will immediately decelerate"
        - "It will drift into circular orbit"
      correct_index: 0  # 0-indexed position of the correct answer
```

---

## 4. Validating Your Content

Before submitting your changes, run the validator from the `backend/` directory:

```bash
make content-validate
```

Or using the CLI directly:

```bash
uv run python -m app.content.cli validate --strict
```

### What the Validator Checks:
1. **Schema Integrity**: Validates all required fields, data types, and difficulty ranges.
2. **Symbolic Formulas**: Verifies that algebraic formulas parse cleanly with the SymPy math engine.
3. **Multiple Choice Indices**: Ensures `correct_index` points to a valid option.
4. **Referential Integrity**: Checks that all `concept_id` references exist.
5. **No Graph Cycles**: Ensures prerequisite chains do not create circular dependency loops.
6. **No Orphan Concepts**: Warns if a concept has zero connections in a multi-concept topic.
7. **Coverage**: Warns if a concept has zero misconceptions or zero problems.

---

## 5. Summary Statistics

You can view an overview of all loaded curriculum content using:

```bash
uv run python -m app.content.cli stats
```
