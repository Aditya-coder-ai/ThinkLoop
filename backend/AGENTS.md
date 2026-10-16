# Thinkloop - Engineering Rules & Architectural Contract

## Architecture Summary
Thinkloop is an AI Socratic tutoring platform built with a high-reliability, async-first Python foundation. Part 1 establishes the production-grade core:
- **Web Layer**: FastAPI with ASGI lifespan management and strict schema validation.
- **Data Layer**: SQLAlchemy 2.x async ORM with `asyncpg`, PostgreSQL 16 (`pgvector` extension enabled), and Alembic migrations.
- **Caching & Rate Limiting**: Redis via `redis-py` asyncio, sliding/fixed window rate limiting with graceful fail-open behavior.
- **Security & Identity**: RS256 JWT verification via JWKS with caching and key-rotation refetch, decoupled auth-provider architecture (Clerk/Supabase compatible), idempotent user get-or-create on authenticated requests.
- **Observability**: Structured JSON logging with correlated `request_id` (via `X-Request-ID`), uniform error response envelopes, non-leaking error handlers.

## Target Structure
```text
backend/
  app/
    main.py              # create_app() factory
    config.py            # Settings (env-driven, fail fast)
    logging.py           # structured JSON logging + request_id
    errors.py            # AppError hierarchy + handlers
    api/
      deps.py            # get_db, get_redis, current_user
      health.py          # /health (liveness), /ready (db+redis)
      me.py              # GET /me
    core/
      security.py        # JWKS fetch/cache, token verification
      rate_limit.py      # Redis sliding/fixed window limiter dependency
    db/
      base.py            # Base declarative model + naming conventions
      session.py         # async engine & sessionmaker factory
      models.py          # User model only
      migrations/        # Alembic environment and migration scripts
    schemas/
      user.py            # UserRead schemas
      error.py           # ErrorResponse schemas
  tests/
    conftest.py          # Pytest fixtures (DB, Redis, Mock JWKS, RSA keys)
    unit/                # Isolated unit tests
    integration/         # API & migration integration tests
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

## Definition of Done (DoD)
- [ ] `make verify` passes from a clean checkout (lint, types, test, migration checks).
- [ ] Test coverage >= 85%.
- [ ] `alembic upgrade head` and `alembic downgrade base` both succeed.
- [ ] `docker-compose up` + `uvicorn` serves `/health` and `/ready`.
- [ ] A real JWT (from the test key) against `GET /me` returns 200 and creates exactly one user idempotently.
- [ ] `.env.example` lists every required variable with descriptive comments.
- [ ] `README.md` documents setup, env vars, running, testing, and adding a router.
- [ ] `PROGRESS.md` contains built features, assumptions, known limitations, and Part 2 next steps.

## Forbidden Actions
- Adding dependencies not listed in the stack without recording the rationale in `PROGRESS.md`.
- Hardcoding secrets, real API keys, or committing a real `.env` file.
- Building out-of-scope features (chat, LLM calls, content loading, mastery, sessions, Claude API code).
- Making external network calls during automated test execution.
- Disabling lint/type rules globally or adding `# type: ignore` / `# noqa` without a written reason.
- Declaring "done" without pasting the full output of `make verify`.
