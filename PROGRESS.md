# Progress & Implementation Record

## Status: Part 1 (Foundation) Complete

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
   - Verified clean upgrade to `head` and downgrade to `base`.

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

### Assumptions
1. **JWKS Token Claims**: Auth provider tokens supply `sub` (or `user_id` / `custom:auth_id`) as the primary identity claim (`auth_id`), and optional `email` claim.
2. **Race-Safe Provisioning**: In high-concurrency environments, user creation utilizes PostgreSQL `ON CONFLICT (auth_id) DO UPDATE` to eliminate duplicate key race conditions across parallel requests.
3. **Hermetic Test Suite**:
   - `tests/conftest.py` uses local RSA 2048-bit keypair generation and mock JWKS endpoints. No external network calls are made during tests.
   - In-memory SQLite (`sqlite+aiosqlite`) and `fakeredis` are used in test runners to guarantee fast, deterministic tests without requiring local background daemons. Real PostgreSQL 16 + pgvector and Redis are exercised in CI service containers.

---

### Dependencies Rationale
1. `aiosqlite`: Added to dev dependencies to enable async SQLite dialect testing without requiring an external database server on developer workstations.
2. `fakeredis[lua]`: Added to dev dependencies to enable full Redis sorted set and pipeline testing in memory hermetically.
3. `types-redis`: Added to dev dependencies for strict mypy typing support with Redis.

---

### Known Limitations
1. **Unauthenticated Rate Limiting by IP**: In production environments behind reverse proxies or load balancers, rate limiting by IP requires configuring trusted proxy headers (`X-Forwarded-For`).
2. **Single-Region Redis**: Rate limiter uses Redis sorted sets in a single cluster/instance. Multi-region latency will require local Redis caches or token bucket algorithms.
3. **Database Dialect in Migrations**: The `0001_initial_users_and_vector.py` migration includes conditional logic for `CREATE EXTENSION IF NOT EXISTS vector` to allow running both on PostgreSQL and SQLite.

---

### Suggested Next Steps for Part 2 (Content System)
1. **Content Schema & Domain Models**:
   - Define models for pedagogical structure: `Topic`, `Subtopic`, `Unit`, `Concept`.
   - Add content chunking schema: `ContentChunk` with text, token count, metadata, and pgvector `vector(1536)` embedding column.
2. **Alembic Migration for Content**:
   - Migration adding content tables, foreign keys, and pgvector cosine/HNSW distance indexes (`CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`).
3. **Content Ingestion & Embedding Service**:
   - Background service to parse markdown / curriculum definitions into chunks and generate vector embeddings.
4. **Semantic Search & Retrieval Dependencies**:
   - FastAPI dependencies and repository layer for similarity search over curriculum chunks using SQLAlchemy pgvector operators (`l2_distance`, `cosine_distance`).
5. **Content API Routes**:
   - `GET /content/topics`: Hierarchical curriculum navigation.
   - `GET /content/chunk/{id}`: Detailed concept retrieval for tutoring sessions.
