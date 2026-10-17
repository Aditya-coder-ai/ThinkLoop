# Progress & Implementation Record

## Status: Part 1 (Foundation) & Part 2 (Content System) Complete

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

---

### Known Limitations
1. **FakeEmbedder in Local Development**: `FakeEmbedder` generates deterministic hash vectors for hermetic CI and test runs. Realistic semantic similarity retrieval requires running with `HttpEmbedder` against an OpenAI/Voyage/Cohere/Gemini compatible embeddings endpoint.
2. **HNSW Vector Indexing on SQLite**: During in-memory SQLite unit testing, pgvector column types fall back to standard column mappings and HNSW vector index statements are ignored. Full HNSW indexing is exercised against live PostgreSQL 16 in CI and docker-compose.

---

### Suggested Next Steps for Part 3 (Chat & Dialogue Session Management)
1. **Dialogue Session State**:
   - Define database models for `DialogueSession`, `Turn`, and `LearnerState` linked to `users`.
   - Store session history with concept tracking and diagnosed misconceptions.
2. **Socratic Strategy Engine**:
   - Implement dialogue turn state machine (e.g., *Elicit*, *Confront*, *Resolve*, *Practice*).
   - Use `RetrievalService` to fetch relevant misconceptions from student messages and select corresponding `conflict_prompt` tasks.
3. **LLM Orchestration & Prompt Crafting**:
   - Secure LLM client provider with streaming response support.
   - Inject retrieved concept definitions, targeted misconceptions, and conflict prompts into the system context while strictly maintaining the Socratic persona.

---

## Neon PostgreSQL Integration Summary

### What Was Built
1. **Neon Connection Engine & Pooling (`app/db/session.py`)**:
   - Resilient URL normalization converting standard `postgresql://` or `postgres://` connection strings to async SQLAlchemy `postgresql+asyncpg://`.
   - Automatic query parameter sanitization for `sslmode=require` mapping to secure SSL context for `asyncpg`.
   - Neon PgBouncer transaction-pooler compatibility (`-pooler.` hostname detection) disabling prepared statement cache (`prepared_statement_cache_size=0`).
   - Connection pool resilience: `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True` (handles idle compute suspension and drops), `pool_recycle=300`.
   - Non-leaking startup / connectivity ping helper (`ping_database`).

2. **Schema & Migration (`0003_learner_profiles_and_mastery.py`, `app/db/models.py`)**:
   - Added `Profile` model (`profiles` table: `user_id` PK, `display_name`, `learning_level`, `exam_target`, `created_at`, `updated_at`).
   - Added `LearnerMastery` model (`learner_mastery` table: `id` PK, `user_id` FK to `profiles.user_id`, `concept_id` FK to `concepts.id`, `mastery_score`, `attempts`, `last_practiced_at`, `next_review_at`, `updated_at`, with `UniqueConstraint("user_id", "concept_id")`).
   - Added `subject` column to `Concept` model and `concepts` table.
   - Idempotent migration that safely inspects live schemas without overwriting or destroying existing data.

3. **Backend-Only Health Probe (`GET /health/db`)**:
   - `GET /health/db`: returns `{"database": "connected"}` (200 OK) when healthy.
   - On error: returns `{"database": "disconnected", "error": "Database connectivity check failed"}` (503 Service Unavailable).
   - Zero disclosure of connection strings, SQL details, or stack traces.

4. **Typed Repository Operations (`app/db/repository.py`)**:
   - `check_db_connectivity`: Lightweight `SELECT 1` ping.
   - `list_concepts`: Active concepts with domain, topic, and subject filters.
   - `get_concept_by_id`: Active concept lookup.
   - `get_learner_profile`: Learner profile lookup by user ID.
   - `upsert_learner_profile`: Idempotent profile creation and field updates.
   - `get_learner_mastery`: Mastery progress lookup.
   - `upsert_learner_mastery`: Idempotent upsert preventing duplicate records, incrementing attempts.

5. **Learner API & Auth Readiness (`app/api/me.py`, `app/schemas/learner.py`)**:
   - `GET /me/profile`: Authenticated user's profile.
   - `PUT /me/profile`: Safely upserts authenticated user's profile.
   - `GET /me/mastery`: Authenticated user's mastery progress.
   - `POST /me/mastery`: Upserts mastery progress with verified ownership.
   - Strict identity derivation from `current_user.auth_id` (browser cannot supply or spoof user IDs).

6. **Automated Test Suite**:
   - `tests/unit/test_neon_session.py`: Connection string parsing, SSL, pooler detection, and error masking.
   - `tests/unit/test_repository.py`: All 7 repository operations, duplicate prevention, and user isolation.
   - `tests/integration/test_db_health.py`: `/health/db` success and failure handling.
   - `tests/integration/test_learner_api.py`: Learner profile, mastery, and auth protection.
   - `tests/integration/test_neon_live.py`: Non-destructive live test against real Neon database when `TEST_DATABASE_URL` is configured.

