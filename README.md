# Thinkloop Backend Foundation

Part 1 (Foundation) of **Thinkloop**, an AI Socratic tutoring platform.

## Architecture
- **Web Framework**: FastAPI with asynchronous route handlers and lifespan management.
- **ORM & Database**: SQLAlchemy 2.x async ORM with `asyncpg`, PostgreSQL 16 with `pgvector`.
- **Migrations**: Alembic with async migration support and downgrade/upgrade cycle verification.
- **Cache & Rate Limiting**: Redis (asyncio `redis-py`) with sliding-window rate limiting and fail-open resilience.
- **Authentication**: RS256 Bearer JWT verification via JWKS key caching (Clerk and Supabase compatible).
- **Observability**: Structured JSON logging with correlated `X-Request-ID` and uniform error envelopes.

---

## Environment Variables

All settings are driven by environment variables and fail fast at startup if missing.

| Variable | Required | Description | Example |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | **Yes** | PostgreSQL connection URL with asyncpg driver | `postgresql+asyncpg://postgres:postgres@localhost:5432/thinkloop` |
| `REDIS_URL` | **Yes** | Redis connection URL for rate limiting and cache | `redis://localhost:6379/0` |
| `AUTH_JWKS_URL` | **Yes** | JWKS endpoint providing RS256 public keys | `https://auth.example.com/.well-known/jwks.json` |
| `AUTH_ISSUER` | **Yes** | Expected JWT `iss` claim | `https://auth.example.com` |
| `AUTH_AUDIENCE` | **Yes** | Expected JWT `aud` claim | `thinkloop-api` |
| `ENVIRONMENT` | No | Target environment (`development`, `test`, `production`) | `development` (default) |
| `LOG_LEVEL` | No | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` (default) |
| `JWKS_CACHE_TTL_SECONDS` | No | JWKS cache TTL in seconds | `3600` (default) |
| `RATE_LIMIT_REQUESTS` | No | Request quota per window | `60` (default) |
| `RATE_LIMIT_WINDOW_SECONDS`| No | Rate limit window in seconds | `60` (default) |

---

## Setup & Running

### 1. Prerequisites
- Python 3.12+
- `uv` package manager (`https://astral.sh/uv`)
- Docker & Docker Compose (optional for local PostgreSQL and Redis)

### 2. Environment Configuration
Copy `.env.example` to `backend/.env`:
```bash
cp backend/.env.example backend/.env
```

### 3. Start Local Services
Launch PostgreSQL (with `pgvector`) and Redis:
```bash
make up
```
*(To stop services: `make down`)*

### 4. Run Migrations
Apply Alembic migrations to head:
```bash
make migrate
```
*(To roll back to base: `make migrate-down`)*

### 5. Run the Application
Start the Uvicorn ASGI server with hot reloading:
```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```
Or use the application factory:
```bash
uv run uvicorn app.main:create_app --factory --reload --port 8000
```

---

## How to Test & Verify

Run individual verification targets or the full suite:

```bash
make lint       # Ruff linting and format checks
make types      # Mypy strict type checking across all modules
make test       # Pytest suite with branch coverage (enforces >= 85%)
make verify     # Complete verification pipeline (lint + types + test + migration up/down check)
```

---

## How to Add a Router

To extend Thinkloop with new endpoints (e.g. for Part 2 Content System or Part 3 Socratic Dialogues):

1. **Create the router file**:
   Add a new file in `backend/app/api/` (for example `backend/app/api/content.py`):
   ```python
   from fastapi import APIRouter, Depends
   from sqlalchemy.ext.asyncio import AsyncSession
   from app.api.deps import get_current_user, get_db, rate_limit
   from app.db.models import User

   router = APIRouter(prefix="/content", tags=["content"])

   @router.get(
       "/modules",
       dependencies=[Depends(rate_limit(limit=30, window_seconds=60))],
   )
   async def list_modules(
       user: User = Depends(get_current_user),
       session: AsyncSession = Depends(get_db),
   ) -> dict[str, str]:
       # Business logic implemented in a service or dependency
       return {"status": "ok", "user_id": str(user.id)}
   ```

2. **Register in `backend/app/main.py`**:
   Import and include your router in `create_app()`:
   ```python
   from app.api.content import router as content_router

   app.include_router(content_router)
   ```

3. **Add automated tests**:
   Add unit or integration tests under `backend/tests/unit/` or `backend/tests/integration/` ensuring authentication, error shapes, and rate limits are validated.
