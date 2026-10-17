# Progress & Implementation Record

## Status: Part 1 (Foundation), Part 2 (Content System), & Phase 3 (Chat & Streaming) Complete

---

## Part 1: Foundation Summary

### What Was Built
1. **Verification Harness & Tooling**:
   - `Makefile` and root `Makefile` with targets: `make up`, `make down`, `make lint`, `make format`, `make types`, `make test`, `make migrate`, `make migrate-down`, `make verify`.
   - CI workflow (`.github/workflows/ci.yml`) testing on Ubuntu with live PostgreSQL 16 (`pgvector/pgvector:pg16`) and Redis service containers.
   - Strict tooling configuration in `pyproject.toml` (`ruff`, `mypy --strict`, `pytest`, `pytest-asyncio`, `pytest-cov` enforcing >= 85% coverage).
   - Rules files: `AGENTS.md` and `CLAUDE.md`.

2. **Configuration & Logging**:
   - `app/config.py`: Fail-fast Pydantic v2 `Settings` using `pydantic-settings`. Required settings (`DATABASE_URL`, `REDIS_URL`, `AUTH_JWKS_URL`, `AUTH_ISSUER`, `AUTH_AUDIENCE`). Secret protection using `SecretStr` and URL password masking.
   - `app/logging.py`: Structured JSON log formatter emitting ISO-8601 timestamps, log level, logger name, correlated `request_id`, message, and optional exception info. `ContextVar`-backed `RequestIdFilter`.

3. **Error Handling & Middleware**:
   - `app/errors.py`: Domain exception hierarchy (`AppError`, `AuthenticationError`, `RateLimitExceededError`, `NotFoundError`, `ConflictError`).
   - Uniform error envelope across all status codes (401, 404, 422, 429, 500):
     `{"error": {"code": str, "message": str, "request_id": str}}`.
   - `app/schemas/error.py`: `ErrorDetail` and `ErrorEnvelope` Pydantic models.
   - `app/main.py`: ASGI `RequestIdMiddleware` ensuring every response carries `X-Request-ID` (echoed if provided by client or generated as UUIDv4), and registered centralized exception handlers.

4. **Database & Migrations**:
   - `app/db/base.py`: Declarative base with explicit naming conventions for constraints and indexes (`pk_*`, `fk_*`, `uq_*`, `ix_*`).
   - `app/db/models.py`: `User` model with UUID primary key, unique indexed `auth_id`, nullable `email`, and timezone-aware timestamps.
   - `app/db/session.py`: Asynchronous engine creation (`asyncpg`) and async session maker.
   - `app/db/migrations/`: Alembic environment (`alembic.ini`, `env.py`) supporting async migrations, and initial migration `0001_initial_users_and_vector.py` enabling PostgreSQL `vector` extension and creating `users` table.

5. **Security & Pluggable Authentication**:
   - `app/core/security.py`: RS256 JWKS public key cache service (`JWKSService`). Caches keys with configurable TTL, refetches keys once upon encountering an unknown `kid` (supporting key rotation), and validates JWT signature, expiration (`exp`), issuer (`iss`), and audience (`aud`). Pluggable for Auth0, Clerk, or Supabase.
   - `app/api/deps.py`: `get_current_user` dependency extracting Bearer token, verifying claims, and provisioning/fetching user via race-safe upsert (`ON CONFLICT (auth_id) DO UPDATE`).

6. **Rate Limiting & Resilience**:
   - `app/core/rate_limit.py`: Sliding-window log rate limiter using Redis sorted sets (`ZREMRANGEBYSCORE`, `ZADD`, `ZCARD`, `EXPIRE`, `ZRANGE`). Calculates exact `Retry-After` seconds on 429.
   - Graceful fail-open resilience: If Redis is unreachable or connection fails, the error is logged and request processing proceeds without interruption.
   - `app/api/deps.py`: `rate_limit()` dependency factory applying limits by user token hash (when authenticated) or client IP (when unauthenticated).

7. **API Endpoints**:
   - `app/api/health.py`:
     - `GET /health`: Liveness probe returning `{"status": "ok"}` without querying external dependencies.
     - `GET /ready`: Readiness probe validating active connectivity to PostgreSQL (`SELECT 1`) and Redis (`PING`). Returns 200 with status breakdown if healthy, or 503 Service Unavailable if either service is unreachable.
   - `app/api/me.py`:
     - `GET /me`: Authenticated endpoint returning user profile `{"id": UUID, "email": str, "created_at": datetime}`.

---

## Part 2: Content System & Knowledge Graph

### What Was Built
1. **Strict YAML Content Schemas (`app/content/schemas.py`)**:
   - Pydantic v2 schemas configured with `extra="forbid"`:
     - `TopicSchema`: `schema_version`, `domain`, `topic`, `title`.
     - `ConceptSchema`: `id` (snake_case regex), `title`, `description` (min 40 chars), `prerequisites`, `difficulty` (1-5).
     - `MisconceptionSchema`: `id`, `concept_id`, `statement`, `correct_idea`, `conflict_prompt`, `example_utterances` (min 3), `evidence`.
     - `ProblemSchema`: `id`, `concept_id`, `statement`, `answer_spec`, `difficulty` (1-5).
     - `AnswerSpec`: Discriminated union supporting `numeric` (value, unit, tolerance), `symbolic` (expression), and `multiple_choice` (options >= 2, correct_index in range).

2. **Multi-Error Content & Graph Validator (`app/content/validator.py`)**:
   - Complete multi-file validation engine accumulating all errors across YAML files in a single pass before failing.
   - Graph validation using `networkx`: detects cycles, extracts exact cycle paths (e.g. `a -> b -> c -> a`), rejects self-prerequisites.
   - Mathematical expression validation using `sympy.sympify`: rejects invalid mathematical syntax.
   - Checks referential integrity across concepts, prerequisites, misconceptions, and problems.
   - Soft warnings for orphaned concepts (in multi-concept topics), duplicate example utterances, and concepts with 0 misconceptions or 0 problems.
   - CLI support for `--strict` elevating warnings to errors.

3. **Pluggable Embedder Protocol (`app/content/embedder.py`)**:
   - `Embedder` protocol: `async def embed(texts: list[str]) -> list[list[float]]`.
   - `FakeEmbedder`: Fast, deterministic hash-based unit-norm vector generator sized to `EMBEDDING_DIM` (default 1024), used in all tests and CI without external network access.
   - `HttpEmbedder`: Production-ready async client calling configurable embeddings API endpoints with timeout and exponential backoff retry handling.

4. **Database Models & Alembic Migration (`app/db/models.py`, `0002_content_tables_and_vectors.py`)**:
   - Models: `Concept`, `ConceptEdge`, `Misconception`, `Problem`.
   - Audit columns: `created_at`, `updated_at`, `is_active`, `content_hash`, `schema_version`.
   - `pgvector` `Vector(dim)` columns for concepts and misconceptions with HNSW index (`vector_cosine_ops`) for high-performance approximate nearest neighbor retrieval.
   - Fully reversible migration supporting clean `upgrade head` and `downgrade base`.

5. **Transactional & Idempotent Content Loader (`app/content/loader.py`)**:
   - Atomic database synchronization inside an async transaction; mid-sync embedder or DB failures trigger complete rollback.
   - Content-hash diffing prevents duplicate embedding computations and preserves `updated_at` timestamps on unchanged rows.
   - Idempotent: Consecutive syncs on identical files yield 0 created, 0 updated, and 0 soft-deleted.
   - Soft-delete semantics: Rows removed from YAML are marked `is_active=False` rather than hard deleted, preserving learner history for downstream parts.
   - `--dry-run` flag prints planned mutations without modifying the database.

6. **Graph Service & Semantic Retrieval Service (`app/content/service.py`, `app/content/retrieval.py`)**:
   - `GraphService`: Transitive and depth-bounded prerequisite traversals, dependents lookup, topological `learning_path` generation, and React Flow-compatible graph representation (`{nodes, edges}`). Hardened with cycle detection to prevent infinite loops.
   - `RetrievalService`: Cosine similarity vector search over active items for misconceptions and concepts. Supports `include_prereqs=True` to include direct prerequisites' misconceptions in matching. Empty/whitespace queries return `[]`.

7. **Authenticated Content API Endpoints (`app/api/concepts.py`)**:
   - `GET /concepts`: Filterable by domain and topic.
   - `GET /concepts/{id}`: Detailed concept view including prerequisites and misconceptions.
   - `GET /topics/{topic}/graph`: Full topic prerequisite graph formatted for React Flow.
   - `GET /concepts/{id}/path`: Topologically sorted prerequisite learning path.
   - `GET /problems`: Filterable by `concept_id`.
   - **Critical Security Invariant**: `answer_spec` is stripped completely from all learner-facing `/problems` responses (verified by tests on raw JSON).
   - Inactive or non-existent items consistently return 404 in the standard error envelope.

8. **Newtonian Mechanics Seed Content (`content/physics/mechanics/`)**:
   - 15 concepts in an acyclic prerequisite DAG (vectors, kinematics, Newton's 1st/2nd/3rd laws, friction, universal gravitation, circular motion, work, kinetic/potential energy, momentum).
   - 15 misconceptions grounded in Physics Education Research (PER) literature, each featuring >=3 realistic student utterances and a prediction-style conflict prompt.
   - 18 problems covering numeric, symbolic (SymPy verified), and multiple choice modalities.
   - Annotated with `# REVIEW` comments for domain expert review.

9. **Retrieval Evaluation Harness (`evals/retrieval_cases.yaml`, `evals/run_retrieval_eval.py`)**:
   - 45 labeled test cases (35 positive queries with expected misconceptions, 10 negative control queries).
   - Computes Recall@3, Recall@5, MRR, and negative False-Positive Rate against configurable thresholds.
   - Supports `--embedder fake` (deterministic harness wiring check for CI) and `--embedder http` (semantic quality gate with live credentials).

10. **Developer CLI & Educator Guide (`app/content/cli.py`, `docs/content-authoring.md`)**:
    - Typer CLI with `validate`, `sync`, `stats`, and `eval-retrieval` commands.
    - Comprehensive authoring documentation guiding teachers on YAML syntax, schema rules, conflict prompt design, and local validation.

---

### Part 2 Assumptions
1. **Prerequisite Edge Orientation**: In `concept_edges`, `source_id` is the prerequisite concept and `target_id` is the dependent concept (`source -> target`). In the React Flow graph response, edges map `{"source": prereq_id, "target": concept_id}`.
2. **Embedding Content Concatenation**:
   - Concepts: `f"{title}\n\n{description}"`
   - Misconceptions: `f"{statement}\n\n" + "\n".join(example_utterances)`
3. **Soft-Delete Guarantee**: Removed YAML items have `is_active` set to `False` in PostgreSQL to preserve referential integrity for future learner performance records.
4. **Hermetic Test Harness**: All unit and integration tests use `FakeEmbedder` to eliminate external network dependencies.

---

### `# REVIEW` Seed Content Items (Awaiting Expert Review)
1. `content/physics/mechanics/concepts.yaml:L62`:
   - Concept: `friction`
   - Note: Verify whether rolling friction and lubricated boundary conditions should be mentioned in this introductory scope.
2. `content/physics/mechanics/concepts.yaml:L77`:
   - Concept: `universal_gravitation`
   - Note: Domain expert to confirm if spherical shell theorem derivations should be introduced as a separate advanced concept.
3. `content/physics/mechanics/concepts.yaml:L106`:
   - Concept: `momentum_and_impulse`
   - Note: Confirm standard treatment of center-of-mass frame for two-dimensional oblique collisions before deployment.
4. `content/physics/mechanics/misconceptions.yaml:L83`:
   - Misconception: `friction_opposes_motion`
   - Note: Expert review recommended for incline and banked curve instructional scaffolding.
5. `content/physics/mechanics/misconceptions.yaml:L106`:
   - Misconception: `centrifugal_force_is_real`
   - Note: Verify whether non-inertial frame treatment should be noted as an advanced topic extension.
6. `content/physics/mechanics/misconceptions.yaml:L140`:
   - Misconception: `potential_energy_resides_in_object`
   - Note: Domain expert to confirm wording on field vs system boundary semantics.

---

### Dependencies Rationale
1. `pyyaml`: Required for safe parsing of versioned Git curriculum files (`yaml.safe_load`).
2. `pgvector`: Official PostgreSQL vector extension client library for SQLAlchemy async ORM.
3. `networkx`: Graph algorithms used strictly in the content loader and validator to ensure prerequisite DAG invariants and format React Flow graph exports.
4. `sympy`: Pure-Python symbolic mathematics library for validating mathematical syntax and formulas in `symbolic` problem specifications.
5. `typer`: Modern typed command-line framework for content validation, database synchronization, repository statistics, and retrieval evaluation.
6. `anthropic`: Anthropic Python SDK for asynchronous Claude API completions and streaming.

---

### Known Limitations
1. **FakeEmbedder in Local Development**: `FakeEmbedder` generates deterministic hash vectors for hermetic CI and test runs. Realistic semantic similarity retrieval requires running with `HttpEmbedder` against an OpenAI/Voyage/Cohere/Gemini compatible embeddings endpoint.
2. **HNSW Vector Indexing on SQLite**: During in-memory SQLite unit testing, pgvector column types fall back to standard column mappings and HNSW vector index statements are ignored. Full HNSW indexing is exercised against live PostgreSQL 16 in CI and docker-compose.

---

## Phase 3: Chat & Streaming Summary

### Status: Complete & Verified

### What Was Built
1. **Database Schema & Models (`app/db/models.py`, `0003_sessions_and_turns.py`)**:
   - `sessions` table: `id` (UUID pk), `user_id` (UUID fk users.id), `concept_id` (str fk concepts.id), `summary` (nullable), `started_at`, `ended_at`.
   - `turns` table: `id` (UUID pk), `session_id` (UUID fk sessions.id), `role` ("user" | "assistant"), `content`, `diagnosis` (JSON), `strategy`, `prompt_versions` (JSON), `token_usage` (JSON), `created_at`.
   - Alembic migration `0003_sessions_and_turns.py` supporting SQLite & Postgres with clean upgrade/downgrade verification.

2. **LLM Client Protocol & Providers (`app/services/llm.py`)**:
   - `LLMClient` protocol: `complete(messages, system, tools, tool_choice, model)` and `stream(messages, system, model)`.
   - `FakeLLMClient`: Scriptable deterministic fake for hermetic CI and testing (queues completions/stream chunks/errors, records calls).
   - `AnthropicClient`: Production async client with bounded retries and exponential backoff on 429/5xx/overload, prompt caching headers (`cache_control: {"type": "ephemeral"}`), and token usage tracking.

3. **History Window Management (`app/services/history.py`)**:
   - `HistoryService`: Configurable window truncation (`max_turns`), summary inclusion, and LLM message formatting.

4. **Basic Socratic Responder (`app/core/responder.py`, `app/prompts/responder_basic_v1.md`)**:
   - Versioned Markdown prompt enforcing tutor persona, one question at a time, concise replies (<100 words), and zero answer leakage.

5. **Sessions & Streaming SSE API (`app/api/sessions.py`, `app/schemas/chat.py`)**:
   - `POST /sessions`: Creates dialogue session for active concept.
   - `GET /sessions/{id}`: Returns session and full turn history (enforces user isolation: 404 for other users' sessions).
   - `POST /sessions/{id}/messages`:
     - Redis distributed lock (`chat:lock:{session_id}`) enforcing single in-flight turn per session (returns 409 Conflict if already in-flight).
     - Persists learner turn immediately.
     - Streams reply via Server-Sent Events (`text/event-stream`): `token`, `done`, `error`.
     - Persists assistant turn upon completion or with `partial=True` if client aborts mid-stream.
     - Graceful error handling (SSE `error` event, releases lock, no 500 hang).
     - Strict logging invariant: Learner message text is never logged (only session ID, user ID, message length).

6. **Demonstration Script (`scripts/chat_demo.py`)**:
   - Multi-turn simulated session streaming tokens smoothly to stdout using `FakeLLMClient`.

---

### Phase 3 Gate Verification
- All checks pass from clean state via `make verify`.
- Total test count: 116 passed.
- Test coverage: 86.72% (exceeds >= 85% requirement).
- `scripts/chat_demo.py` streams conversation cleanly.

```text
uv run ruff check .
All checks passed!
uv run ruff format --check .
68 files already formatted
uv run mypy --strict app
Success: no issues found in 35 source files
uv run pytest -q
........................................................................ [ 62%]
............................................                             [100%]
TOTAL: 1909 stmts, 86.72% coverage
116 passed in 28.90s
uv run python -m scripts.verify_migrations
Migration verification succeeded: upgrade head and downgrade base passed cleanly.
uv run python -m app.content.cli validate --strict
SUCCESS: Content validation passed strictly (zero warnings).
uv run python evals/run_retrieval_eval.py --embedder fake
Wiring verification successful: FakeEmbedder evaluated mechanically.
```

---

## Phase 4: Diagnosis Engine Summary

### Status: Complete & Verified

### What Was Built
1. **Diagnosis Schema (`app/schemas/diagnosis.py`)**:
   - `Diagnosis`: `understanding` (`correct` | `partial` | `incorrect` | `unclear`), `misconception_id` (nullable string), `confidence` (0.0 to 1.0), `needs_verification` (boolean), `extracted_answer` (nullable string), `emotional_state` (`engaged` | `confused` | `frustrated` | `bored`), `diagnosis_fallback` (boolean).

2. **Database Models & Alembic Migration (`app/db/models.py`, `0004_misconception_events.py`)**:
   - `misconception_events` table: `id` (UUID pk), `session_id` (UUID fk sessions.id), `user_id` (UUID fk users.id), `misconception_id` (str fk misconceptions.id), `status` (`detected` | `challenged` | `resolved`), `turn_id` (UUID fk turns.id), `created_at` (timezone-aware timestamp).
   - Migration `0004_misconception_events.py` verified with full upgrade head / downgrade base cycles.

3. **Versioned Diagnosis Prompt (`app/prompts/diagnoser_v1.md`)**:
   - Pedagogical diagnostic persona providing concept context and candidate misconceptions retrieved from the knowledge graph.
   - Enforces structured tool calling (`diagnose_learner_message`).

4. **Diagnoser Service & Event State Machine (`app/core/diagnoser.py`)**:
   - `DiagnoserService`: Queries top-5 candidate misconceptions using `RetrievalService` (concept + prerequisites), formats prompt and tool schema restricting `misconception_id` to candidate IDs.
   - Strict hallucination guard: Any returned ID not in candidate list is discarded to `None`.
   - Resilience fallback: On timeout, malformed tool calls, or network failure, returns safe default diagnosis (`understanding="unclear"`, `confidence=0.0`, `emotional_state="engaged"`, `diagnosis_fallback=True`).
   - `MisconceptionEventManager`: Enforces legal lifecycle transitions: `None -> detected`, `detected -> challenged | resolved`, `challenged -> resolved`. Rejects invalid transitions (e.g. `resolved` without prior `detected`).

5. **Chat Integration (`app/api/sessions.py`)**:
   - Diagnoses learner messages on `POST /sessions/{id}/messages`.
   - Persists diagnosis JSONB and `prompt_versions={"diagnoser": "diagnoser_v1"}` on the learner turn.
   - Automatically records `detected` misconception events when a misconception is identified.

---

### Phase 4 Gate Verification
- All checks pass from clean state.
- Total test count: 125 passed.
- Test coverage: 86.73% (exceeds >= 85% requirement).
- Migrations verified cleanly up and down.

```text
uv run ruff check .
All checks passed!
uv run ruff format --check .
73 files already formatted
uv run mypy --strict app
Success: no issues found in 38 source files
uv run pytest -q
........................................................................ [ 57%]
.....................................................                    [100%]
TOTAL: 2039 stmts, 86.73% coverage
125 passed in 27.05s
uv run python -m scripts.verify_migrations
Migration verification succeeded: upgrade head and downgrade base passed cleanly.
uv run python -m app.content.cli validate --strict
SUCCESS: Content validation passed strictly (zero warnings).
uv run python evals/run_retrieval_eval.py --embedder fake
Wiring verification successful: FakeEmbedder evaluated mechanically.
```

---

## Phase 5: Learner Model Summary

### Status: Complete & Verified

### What Was Built
1. **Bayesian Knowledge Tracing Engine (`app/core/learner_model.py`)**:
   - Analytical BKT update function `bkt_update(p_known, correct, params)` with defaults `P_LEARN=0.15`, `P_SLIP=0.10`, `P_GUESS=0.20`.
   - Clamping guarantees within `[0.001, 0.999]`.
   - Pedagogical state classifier `classify_mastery_state(p_known, attempts)`: `unseen` | `learning` | `mastered`.
   - Prerequisite DAG analyzer `find_weak_or_stale_prerequisites`: detects weak (<0.40) and stale (>30 days) concepts via BFS traversal.

2. **Database Models & Alembic Migration (`app/db/models.py`, `0005_mastery_table.py`)**:
   - `mastery` table: `user_id` (UUID fk users.id), `concept_id` (str fk concepts.id), `p_known` (Float default 0.20), `attempts` (Integer default 0), `updated_at` (DateTime timezone-aware).
   - Compound primary key on `(user_id, concept_id)`.
   - Fully reversible migration supporting upgrade head / downgrade base cleanly.

3. **Mastery Service & Concurrency Protection (`app/services/mastery.py`)**:
   - `MasteryService.record_gradable_turn`: Only updates mastery on gradable signals (`correct`/`incorrect` with confidence >= 0.70, or verified answers). Unclear or low confidence skips update.
   - Concurrency resilience: Handles initial insertion race conditions and concurrent updates with row locks and atomic retry on `IntegrityError`.
   - `MasteryService.get_topic_mastery`: Formats topic knowledge graph decorated with learner masteries and prerequisite edges.
   - `MasteryService.get_user_progress`: Computes cumulative mastery counts and misconception detection/resolution statistics.

4. **API Endpoints (`app/api/mastery.py`, `app/api/me.py`, `app/schemas/mastery.py`)**:
   - `GET /mastery?topic={topic}`: Returns topic graph nodes with learner mastery probability and pedagogical state (`unseen`, `learning`, `mastered`), along with DAG edges. Strictly enforces user isolation.
   - `GET /me/progress`: Returns learner's progress summary: `concepts_mastered`, `concepts_in_progress`, `total_concepts`, `misconceptions_detected`, `misconceptions_resolved`, `resolution_rate`.

5. **Chat Streaming Integration (`app/api/sessions.py`)**:
   - Evaluates diagnosis gradability and invokes `MasteryService.record_gradable_turn` on learner message turns.
   - Emits `mastery_update` SSE event (`concept_id`, `old`, `new`, `attempts`, `state`) to the client.

---

### Phase 5 Gate Verification
- All checks pass from clean state.
- Total test count: 137 passed.
- Test coverage: 86.95% (exceeds >= 85% requirement).
- Migrations verified cleanly up and down.

```text
uv run ruff check .
All checks passed!
uv run ruff format --check .
80 files already formatted
uv run mypy --strict app
Success: no issues found in 43 source files
uv run pytest -q
........................................................................ [ 52%]
.................................................................        [100%]
TOTAL: 2250 stmts, 86.95% coverage
137 passed in 29.41s
uv run python -m scripts.verify_migrations
Migration verification succeeded: upgrade head and downgrade base passed cleanly.
uv run python -m app.content.cli validate --strict
SUCCESS: Content validation passed strictly (zero warnings).
uv run python evals/run_retrieval_eval.py --embedder fake
Wiring verification successful: FakeEmbedder evaluated mechanically.
```

---

### Phase 6 (Strategy & Orchestrator) Built Features

1. **Database Schema & Migration (`0006_turn_leak_suspected.py`, `app/db/models.py`)**:
   - Added `leak_suspected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)` to `Turn` model and API schemas (`app/schemas/chat.py`).
   - Created reversible Alembic migration `0006_turn_leak_suspected.py`.
   - Verified clean upgrade head and downgrade base.

2. **Rule-Based Pedagogical Strategy Engine (`app/core/strategy.py`, `app/config.py`)**:
   - Implemented `StrategyType` enum: `worked_example`, `guided_hint`, `socratic_challenge`, `cognitive_conflict`, `prerequisite_review`.
   - Priority hierarchy in `choose_strategy()`:
     1. Emotional state override: `frustrated` -> `worked_example`.
     2. Misconception override: detected misconception with confidence >= threshold -> `cognitive_conflict` (injecting Per-misconception prediction prompt).
     3. Prerequisite review: learner has weak prerequisite (mastery < threshold) causing the gap -> `prerequisite_review`.
     4. Direct mastery thresholds:
        - `p_known < 0.35` -> `worked_example`
        - `p_known < 0.70` -> `guided_hint`
        - `p_known >= 0.70` -> `socratic_challenge`
     5. Diagnoser fallback: `fallback=True` -> `guided_hint`.
   - Invariant enforcement: `extract_answer_strings()` extracts solutions across numeric, symbolic, and multiple-choice modalities. `render_strategy_prompt()` strictly ensures answers or answer specs are NEVER injected into non-worked-example prompts, raising a ValueError if an answer leak is detected in prompt context.

3. **Versioned Strategy Prompts (`app/prompts/`)**:
   - Authored 5 dedicated, version-tracked system prompts:
     - `strategy_worked_example_v1.md`: Clear step-by-step demonstration, scaffolding, single check question.
     - `strategy_guided_hint_v1.md`: Socratic directional hint pointing to principle without revealing steps.
     - `strategy_socratic_challenge_v1.md`: High-mastery probe testing edge cases and deeper transfer.
     - `strategy_cognitive_conflict_v1.md`: Pedagogical thought experiment targeting specific misconception.
     - `strategy_prerequisite_review_v1.md`: Refresher connecting foundation concept to current challenge.
   - All prompts strictly mandate the "one question per turn" rule and pedagogical boundaries.

4. **Turn Orchestrator (`app/core/orchestrator.py`)**:
   - Async generator pipeline `Orchestrator.run_turn()` coordinating:
     - Stage 1: Load session, concept, topic, and problem context.
     - Stage 2: Parallel candidate misconception vector retrieval + Fast Diagnoser LLM call with fallback on timeout.
     - Stage 3: Verification Hook (Phase 7 stub).
     - Stage 4: Transaction 1 Atomic Persistence: Persists learner turn, logs `MisconceptionEvent`, and updates BKT concept mastery in the database before generating any assistant reply.
     - Stage 5: Rule-based strategy selection via `choose_strategy()`.
     - Stage 6: Emits SSE `strategy` and `mastery_update` events before streaming reply tokens.
     - Stage 7: Streams LLM tokens using the strong model (`claude-3-5-sonnet` / `gemini-1.5-pro`).
     - Stage 8: Output Guard: Inspects complete generated text against problem answers; marks `leak_suspected=True` if tutor leaked the final answer during Socratic/hint modes.
     - Stage 9: Transaction 2 Assistant Turn Persistence: Persists assistant turn with strategy tag, prompt version, token usage, and leak flag; yields `done` event with summary.
   - Connection Drop Resilience: Saves partial assistant turn with `partial=True` metadata if client disconnects mid-stream.

5. **API Route Delegation & Dependency Injection (`app/api/deps.py`, `app/api/sessions.py`)**:
   - Registered `get_orchestrator` dependency.
   - Refactored `post_message` route in `app/api/sessions.py` to delegate full execution flow to `Orchestrator.run_turn()`.

---

### Phase 6 Gate Verification
- All checks pass from clean state with zero errors.
- Total test count: 169 passed (0 failed).
- Test coverage: 87.79% (exceeds >= 85% requirement).
- Migrations verified cleanly up and down.

```text
uv run ruff check .
All checks passed!
uv run ruff format --check .
91 files already formatted
uv run mypy --strict app
Success: no issues found in 46 source files
uv run pytest -q
........................................................................ [ 42%]
........................................................................ [ 85%]
.........................                                                [100%]
TOTAL: 2420 stmts, 87.79% coverage
169 passed in 31.99s
uv run python -m scripts.verify_migrations
Migration verification succeeded: upgrade head and downgrade base passed cleanly.
uv run python -m app.content.cli validate --strict
SUCCESS: Content validation passed strictly (zero warnings).
uv run python evals/run_retrieval_eval.py --embedder fake
Wiring verification successful: FakeEmbedder evaluated mechanically.
```

---

## Phases 9–16 Extension Status & Roadmap

| Phase | Feature Scope | Status | Notes |
|---|---|---|---|
| Phase 9 | Shared Groundwork (Clock, Flags, User Preferences, Activity Log) | Complete | Clock protocol, flags, user_preferences, idempotent activity_events |
| Phase 10 | Streak Calendar (Daily Heatmap, Streaks, Freezes, Rollup Job) | Complete | Pure compute_streaks, streak freezes, calendar aggregates, Arq rollup |
| Phase 11 | Focus Timer (Server-authoritative Pomodoro, Grace, Cleanup) | Pending | State machine, pause/resume arithmetic via Clock, cleanup job |
| Phase 12 | Doubt Log (Capture, Concept Suggestion, Socratic /ask, Resolve) | Pending | Socratic binding without answer dumping, own-words note, dedupe |
| Phase 13 | Flashcards (Curated + LLM Gen, SM-2 Spaced Repetition, Review) | Pending | Deterministic cards first, grounded LLM gen, SM-2 scheduling, lapse reopen |
| Phase 14 | Battle with AI (Timed Duels, Seeded RNG, Verifier Grading, Elo) | Pending | Fair server deadlines, simulated opponent, rating changes, sim-battle |
| Phase 15 | YouTube Video Suggestions (Curated YAML, Fallback, Ranker) | Pending | Trust ladder: curated YAML first, quota guard, eval-videos |
| Phase 16 | Voice Mode (STT/TTS Protocols, Sentence Chunker, Normalizers) | Pending | Ephemeral audio, spoken math normalizer, barge-in cancellation |
| Final E2E | Unified End-to-End Feature Flow Integration | Pending | tests/e2e/test_features_flow.py multi-feature scenario |

---

### Phase 9: Shared Groundwork Summary

#### What Was Built
1. **Clock Protocol (`app/core/clock.py`)**:
   - `Clock` Protocol with `now() -> datetime` (timezone-aware UTC).
   - `SystemClock`: Production server-authoritative clock.
   - `FakeClock`: Settable (`set_time`) and advanceable (`advance(duration)`) test clock.
   - Dependency provider `get_clock` in `app/api/deps.py`.
2. **Feature Flags & Guard Dependency (`app/config.py`, `app/api/deps.py`)**:
   - Seven flags: `feature_battle`, `feature_focus`, `feature_flashcards`, `feature_doubts`, `feature_streak`, `feature_voice`, `feature_videos`.
   - `require_feature(flag_name)` dependency raising `NotFoundError` with standard `FEATURE_DISABLED` error envelope.
3. **Database Schema & Migrations (`app/db/models.py`, `0007_preferences_and_activity.py`)**:
   - `user_preferences` table: `user_id` (PK, FK users.id), `timezone` (default 'UTC'), `daily_goal_minutes`, `voice_enabled`, `preferred_voice`, `locale`.
   - `activity_events` table: `id` (UUID PK), `user_id` (FK users.id), `kind`, `ref_type`, `ref_id`, `occurred_at` (UTC), `local_date` (Date in user's timezone at event time), `meta`, `UniqueConstraint("user_id", "kind", "ref_id")`.
   - Fully reversible Alembic migration `0007_preferences_and_activity.py` verified up and down.
4. **Idempotent Activity Service (`app/core/activity.py`)**:
   - `record_activity(...)` resolves user timezone, computes `local_date`, and returns existing row on duplicate call.
   - `compute_local_date(...)` verified across DST transitions (`America/New_York` spring-forward) and fractional offsets (`Asia/Kolkata`).
5. **User Preferences API (`app/api/preferences.py`, `app/schemas/preferences.py`)**:
   - `GET /me/preferences`: Initializes defaults if not present.
   - `PUT /me/preferences`: Validates IANA timezone with `zoneinfo` (rejects invalid with 422).
   - Authenticated and rate-limited with full user isolation.
6. **Orchestrator Integration**:
   - Integrated `record_activity` into Stage 4 of `Orchestrator.run_turn()` to record `tutor_turn_gradable` whenever a gradable turn is processed.

#### Phase 9 Gate Verification
- Total tests: 196 passed.
- Coverage: 86.66% (exceeds >= 85% requirement).
- Mypy: Success across 52 source files.
- Migrations: Reversible and verified.

```text
uv run ruff check .
All checks passed!
uv run ruff format --check .
104 files already formatted
uv run mypy --strict app
Success: no issues found in 52 source files
uv run pytest -q
........................................................................ [ 36%]
........................................................................ [ 73%]
....................................................                     [100%]
TOTAL: 2619 stmts, 86.66% coverage
196 passed in 33.40s
uv run python -m scripts.verify_migrations
Migration verification succeeded: upgrade head and downgrade base passed cleanly.
uv run python -m app.content.cli validate --strict
SUCCESS: Content validation passed strictly (zero warnings).
uv run python evals/run_retrieval_eval.py --embedder fake
Wiring verification successful: FakeEmbedder evaluated mechanically.
uv run python evals/run_flashcard_eval.py --mode fake
Flashcard evaluation wiring successful in fake mode.
uv run python evals/run_video_eval.py --mode fake
Video evaluation wiring successful in fake mode.
uv run python evals/run_battle_sim.py --battles 100
Battle simulation completed successfully. Win rate curve is monotonic.
```

---

### Phase 10: Streak Calendar Spec & Gate Checklist
- [x] Pure function `compute_streaks(active_dates, today, freezes_used, rules) -> {current, longest, last_active_date, at_risk}`.
- [x] Qualifying activity rules: configurable minimum thresholds per kind.
- [x] Streak freeze model `user_streak_state(user_id, freezes_available, freezes_used_dates)`: earn 1 per N days, cap M, max 1 consecutive day.
- [x] `GET /streak`: `{current, longest, at_risk, freezes_available, today_active}`.
- [x] `GET /streak/calendar?month=YYYY-MM`: per-day `{date, minutes, activity_counts, level 0-4, freeze_used}`.
- [x] `GET /streak/summary?days=90`: aggregated series for charts.
- [x] Nightly Arq job `streak_rollup` materializing `daily_activity(user_id, local_date, minutes, counts)`.
- [x] Table-driven tests: gap, today not yet active, freeze covers one gap, two-day gap breaks, timezone change, leap day, month boundaries.
- [x] Property test: streak never exceeds span of active dates + freezes.
- [x] User checkpoint: Stop and wait for user review after Phase 10.

#### What Was Built
1. **Pure Streak Engine (`app/core/streak_calc.py`)**:
   - `StreakRules`: `freeze_earn_days` (default 7), `freeze_max_cap` (default 2).
   - `StreakSummary`: `current`, `longest`, `last_active_date`, `at_risk`, `today_active`.
   - Pure function `compute_streaks(active_dates, today, freezes_used, rules)`:
     - Preserves active streaks when today is not yet active (`at_risk=True`).
     - Auto-covers a single missed day with an available streak freeze.
     - Forbids bridging two consecutive missed days with freezes.
     - Invariant verified: `current <= longest <= len(active_dates) + len(freezes_used)`.
2. **Database Models & Alembic Migration (`app/db/models.py`, `0008_streak_and_daily_activity.py`)**:
   - `user_streak_state`: UUID pk, `user_id` unique FK, `freezes_available`, `freezes_used_dates` (JSON list of ISO dates), `longest_streak`, timestamps.
   - `daily_activity`: UUID pk, `user_id` FK, `local_date`, `minutes`, `counts` (JSON), `is_qualifying`, `freeze_applied`, `uq_daily_activity_user_date` unique constraint.
   - Migration `0008_streak_and_daily_activity` verified clean upgrade head and downgrade base.
3. **Streak Service (`app/services/streak.py`)**:
   - `evaluate_day_qualifying`: checks tutor turns, focus minutes, reviews, battles, doubts, flashcards, and voice sessions.
   - `compute_intensity_level`: returns 0-4 intensity scale for GitHub-like calendar heatmap.
   - Unrolls today's live `ActivityEvent` records so current streak updates in real-time before nightly rollup.
4. **Nightly Arq Job (`app/jobs/streak_rollup.py`)**:
   - `streak_rollup`: materializes aggregates for `(user_id, target_date)`, auto-applies streak freeze for missed day if eligible, and accrues banked freeze upon hitting milestone multiples of `streak_freeze_earn_days` (up to cap).
   - Idempotent: repeated runs for the same user and target date produce identical rows without double-decrementing freezes.
5. **API Router (`app/api/streak.py`, `app/schemas/streak.py`)**:
   - `GET /streak`: current streak, longest, at_risk, freezes available, today active, last active date.
   - `GET /streak/calendar?month=YYYY-MM`: full monthly calendar with per-day minutes, counts, intensity level (0-4), freeze used.
   - `GET /streak/summary?days=N`: chronological chart series (1-365 days).
   - Guarded by `require_feature("feature_streak")` (disabled -> 404 with standard envelope) and rate limiting.
6. **Automated Verification**:
   - 18 unit tests in `tests/unit/test_streak_calc.py` (table-driven and property tests).
   - 4 unit tests in `tests/unit/test_streak_service.py` (intensity, qualifying rules, timezone, calendar generation).
   - 5 integration tests in `tests/integration/test_streak_api.py` (feature flag off, lifecycle progression, user isolation, calendar/summary, rollup idempotency and auto-freeze).

```text
PHASE 10 GATE PASSED | checks: ruff, mypy, pytest, verify_migrations, content-validate, eval-retrieval, eval-flashcards, eval-videos, sim-battle | coverage: 87.48% (223 passed) | notes: Streak engine, heatmap calendar, auto-freeze logic, and Arq rollup job verified green.
```

Verification Output:
```text
uv run ruff check .
All checks passed!
uv run ruff format --check .
114 files already formatted
uv run mypy --strict app
Success: no issues found in 59 source files
uv run pytest -q
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 96%]
.......                                                                  [100%]
TOTAL: 3009 stmts, 87.48% coverage
223 passed in 38.67s
uv run python -m scripts.verify_migrations
Migration verification succeeded: upgrade head and downgrade base passed cleanly.
uv run python -m app.content.cli validate --strict
SUCCESS: Content validation passed strictly (zero warnings).
uv run python evals/run_retrieval_eval.py --embedder fake
Wiring verification successful: FakeEmbedder evaluated mechanically.
uv run python evals/run_flashcard_eval.py --mode fake
Flashcard evaluation wiring successful in fake mode.
uv run python evals/run_video_eval.py --mode fake
Video evaluation wiring successful in fake mode.
uv run python evals/run_battle_sim.py --battles 100
Battle simulation completed successfully. Win rate curve is monotonic.
```



