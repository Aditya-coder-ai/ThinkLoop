# Thinkloop - Engineering Rules & Architectural Contract

## Architecture Summary
Thinkloop is an AI Socratic tutoring platform built with a high-reliability, async-first Python foundation.

### Part 1: Core Foundation
- **Web Layer**: FastAPI with ASGI lifespan management and strict schema validation.
- **Data Layer**: SQLAlchemy 2.x async ORM with `asyncpg`, PostgreSQL 16 (`pgvector` extension enabled), and Alembic migrations.
- **Caching & Rate Limiting**: Redis via `redis-py` asyncio, sliding/fixed window rate limiting with graceful fail-open behavior.
- **Security & Identity**: RS256 JWT verification via JWKS with caching and key-rotation refetch, decoupled auth-provider architecture (Clerk/Supabase compatible), idempotent user get-or-create on authenticated requests.
- **Observability**: Structured JSON logging with correlated `request_id` (via `X-Request-ID`), uniform error response envelopes, non-leaking error handlers.

### Part 2: Content System & Knowledge Graph
- **Source of Truth**: Versioned YAML files in Git (`content/<domain>/<topic>/`) containing topic metadata, concepts, prerequisite edges, misconceptions, and problems.
- **Database Synchronization**: The database is a derived cache of the YAML files. Sync is idempotent, transactional, and all-or-nothing. Removed rows are soft-deleted (`is_active=false`), never hard-deleted.
- **Graph & Cross-File Validation**: `networkx` validates directed acyclic graph (DAG) invariants, prerequisite cycles, self-prerequisites, and orphaned nodes before DB writes. Symbolic math expressions validate with `sympy.sympify`.
- **Vector Embeddings**: Embedding generation sits behind an `Embedder` protocol:
  - `FakeEmbedder`: Deterministic hash-based unit-norm vectors used in all tests and CI.
  - `HttpEmbedder`: Provider-agnostic HTTP client for remote embeddings endpoints (dimension configurable via `EMBEDDING_DIM`, default 1024).
- **Retrieval & Graph Services**: Vector cosine similarity retrieval for concepts and misconceptions with prerequisite expansion. Read-side graph traversals for learning paths and prerequisites with infinite-loop guards.
- **API Security**: Authenticated, rate-limited endpoints. Learner-facing endpoints strictly strip `answer_spec` to ensure answers never leave the server.

## Target Structure
```text
backend/
  content/
    physics/mechanics/
      topic.yaml            # topic metadata + schema_version
      concepts.yaml
      misconceptions.yaml
      problems.yaml
  app/
    main.py              # create_app() factory
    config.py            # Settings (env-driven, fail fast)
    logging.py           # structured JSON logging + request_id
    errors.py            # AppError hierarchy + handlers
    api/
      deps.py            # get_db, get_redis, current_user, rate_limit
      health.py          # /health (liveness), /ready (db+redis)
      me.py              # GET /me
      concepts.py        # /concepts, /topics/{topic}/graph, /problems
    content/
      schemas.py         # Pydantic models for YAML (strict, extra=forbid)
      validator.py       # file + cross-file validation, graph DAG checks
      loader.py          # YAML -> Postgres sync (idempotent, transactional)
      embedder.py        # Embedder protocol, FakeEmbedder, HttpEmbedder
      retrieval.py       # vector search + filters
      service.py         # read-side graph & lookups service
      cli.py             # Typer CLI: validate, sync, stats, eval-retrieval
    core/
      security.py        # JWKS fetch/cache, token verification
      rate_limit.py      # Redis sliding-window limiter dependency
    db/
      base.py            # Base declarative model + naming conventions
      session.py         # async engine & sessionmaker factory
      models.py          # User, Concept, ConceptEdge, Misconception, Problem
      migrations/        # Alembic environment and migration scripts
    schemas/
      user.py            # UserRead schemas
      error.py           # ErrorResponse schemas
      content.py         # API response models
  evals/
    retrieval_cases.yaml # labeled retrieval evaluation dataset
    run_retrieval_eval.py# evaluation runner (Recall@k, MRR, FP rate)
  tests/
    conftest.py          # Pytest fixtures (DB, Redis, Mock JWKS, RSA keys, Embedder)
    unit/                # Isolated unit tests
    integration/         # API & migration integration tests
    content/             # Tests validating real seed YAML content
  docs/
    content-authoring.md # Guide for non-engineers (teachers/authors)
  AGENTS.md              # Rules and architectural contract
  CLAUDE.md              # Mirror of AGENTS.md
  PROGRESS.md            # Progress log, assumptions, and next steps
  Makefile               # Verification & dev targets
  docker-compose.yml     # Local services (Postgres 16 + pgvector, Redis)
  pyproject.toml         # Tooling and dependency specifications
  .env.example           # Documented environment template
  .github/workflows/ci.yml # Automated CI pipeline
```

## Coding Conventions
1. **Strict Type Annotations**: Type hints everywhere. Every function, method, parameter, and return value must be strictly typed. Checked with `mypy --strict`.
2. **Async Only**: All I/O paths (database, Redis, HTTP calls) must be purely asynchronous. No blocking calls in async event loop paths.
3. **No Business Logic in Routes**: Route handlers only parse request parameters, call service/database dependencies, and return response schemas. Logic belongs in core modules, dependencies, or domain services.
4. **Dependency Injection**: Inject all database sessions, Redis clients, configuration, authenticated users, and rate limiters via FastAPI `Depends()`.
5. **Fail-Fast Configuration**: Validate all environment settings on startup using Pydantic v2 `BaseSettings`. Refuse to start with clear, descriptive errors if required variables are missing. Never log secrets or tokens.
6. **Uniform Error Envelope**: All API error responses must adhere to:
   ```json
   {
     "error": {
       "code": "STRING_CODE",
       "message": "Human-readable description",
       "request_id": "uuid-string"
     }
   }
   ```
   No unhandled tracebacks may ever be exposed to clients.
7. **Traceability**: Every HTTP request receives or generates an `X-Request-ID` header. Every log entry emitted during that request lifecycle includes the `request_id`.
8. **Content Invariants**:
   - YAML is the source of truth; DB is a derived cache of it.
   - `answer_spec` NEVER leaves the server via learner-facing endpoints.
   - Tests NEVER call real embedding services (use `FakeEmbedder` in tests).
   - Safe YAML loading only (`yaml.safe_load`).
   - No hard DELETEs of content rows; sync soft-deletes via `is_active=False`.

## Post-Login Authentication & Lifecycle Rules
1. **Backend Auth Gating**:
   - Production path: Verify RS256 JWT via cached JWKS (`JWKSService.verify_token`).
   - Dev token path (`dev_<name>`): Accepted ONLY when `AUTH_DEV_MODE=true` AND `ENVIRONMENT != "production"`.
   - If `AUTH_DEV_MODE=true` while `ENVIRONMENT=production`, the application MUST refuse to boot on startup.
   - Dev user IDs are derived deterministically (e.g. `uuid5`), and handles are length/charset-limited (no SQL/path/log injection).
   - Never log tokens. Log user IDs only.
2. **Session Bootstrap & Single Auth Store**:
   - Central module in `frontend/lib/auth/` owns authentication state machine: `loading` -> `authenticated` | `unauthenticated` | `error`.
   - On `/workspace` mount, render loading skeleton without flashing authenticated/unauthenticated UI. Call `GET /me`.
   - If `200`: Reconcile server identity, overwrite cached profile, transition to `authenticated`.
   - If `401`: Execute `clearAllUserState()`, redirect to `/?reason=expired`.
   - If `5xx` / network error: Transition to `error` with backoff retry button (do NOT log user out, do NOT show another user's data).
   - If cached user ID differs from server ID: Run `clearAllUserState()` before rendering anything.
3. **User-Scoped Storage & Clean Sign-Out**:
   - All user data keys must be namespaced `thinkloop:<userId>:<key>` or registered in `lib/auth/storageRegistry.ts`.
   - `clearAllUserState()` purges all user-scoped keys, auth tokens, timers, and active streams.
   - On sign-in, run `clearAllUserState()` first to prevent leftover data leakage between users.
   - On sign-out: Abort in-flight requests, call `POST /backend-api/auth/logout` (2s timeout), run `clearAllUserState()`, broadcast logout across tabs via `BroadcastChannel`, and redirect to `/`.
4. **Resilient Request Execution (`fetchWithAuth`)**:
   - Single-flight 401 handling prevents duplicate sign-out cascades from concurrent failures.
   - Epoch-based `AbortController`: Sign-out increments the epoch and aborts active requests. Responses arriving after sign-out are discarded.
   - Surface 429 `Retry-After` without trigger storms.

## Definition of Done (DoD)
- [ ] `make verify` passes from a clean checkout (lint, types, test, migration checks, content validation, retrieval eval wiring test).
- [ ] Part 1 foundation tests and endpoints continue to pass without regression.
- [ ] Total test coverage >= 85%.
- [ ] `content-validate --strict` passes on the real seed content with zero errors.
- [ ] Seed content meets minimums: >=14 concepts (valid DAG), >=12 misconceptions, >=16 problems, every misconception has >=3 utterances + a prediction prompt.
- [ ] `sync` run twice -> second run reports 0 changes (idempotent, no updated_at churn).
- [ ] Migration upgrade head / downgrade works with pgvector columns + HNSW index.
- [ ] Retrieval eval runs in fake mode (wiring test) and in http mode when credentials exist.
- [ ] API: all 5 content endpoints work; `answer_spec` is never exposed in `/problems`.
- [ ] `docs/content-authoring.md` enables non-engineers to author content and run validation.
- [ ] `PROGRESS.md` records built features, assumptions, `# REVIEW` content list, known limitations, and Part 3 next steps.

## Forbidden Actions
- Any Claude / LLM API calls (out of scope for Part 2).
- Hardcoding secrets, real API keys, or committing a real `.env` file.
- Making external network calls during automated test execution.
- Disabling lint/type rules globally or adding `# type: ignore` / `# noqa` without a written reason.
- Hard-deleting content rows or using unsafe `yaml.load`.
- Returning `answer_spec` or `correct_index` from learner-facing endpoints.
- Presenting unverified seed content as expert-verified (maintain honest `# REVIEW` markers).
- Declaring "done" without pasting the full output of `make verify`.
