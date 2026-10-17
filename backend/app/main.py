import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.concepts import router as concepts_router
from app.api.health import router as health_router
from app.api.mastery import router as mastery_router
from app.api.me import router as me_router
from app.api.preferences import router as preferences_router
from app.api.sessions import router as sessions_router
from app.api.streak import router as streak_router
from app.config import Settings, get_settings
from app.core.security import JWKSService
from app.db.session import create_engine, create_session_factory, ping_database
from app.errors import setup_exception_handlers
from app.logging import configure_logging, set_request_id

logger = logging.getLogger(__name__)



class RequestIdMiddleware(BaseHTTPMiddleware):
    """Propagate or generate X-Request-ID for every HTTP request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Accept incoming X-Request-ID or generate new UUID4
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        set_request_id(req_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Startup
        configure_logging(level=app_settings.log_level)

        engine = create_engine(app_settings.database_url)
        session_factory = create_session_factory(engine)
        redis_client = Redis.from_url(
            app_settings.redis_url,
            decode_responses=True,
        )
        jwks_service = JWKSService(
            jwks_url=str(app_settings.auth_jwks_url),
            ttl_seconds=app_settings.jwks_cache_ttl_seconds,
        )

        app.state.settings = app_settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.redis = redis_client
        app.state.jwks_service = jwks_service

        # Safe startup database connectivity validation
        is_db_connected = await ping_database(engine)
        if is_db_connected:
            logger.info("Database connectivity verified on startup")
        else:
            logger.warning(
                "Database connectivity probe failed on startup; will retry on demand"
            )

        yield

        # Shutdown
        res = redis_client.close()
        if hasattr(res, "__await__"):
            await res
        await engine.dispose()

    app = FastAPI(
        title="Thinkloop API",
        description="FastAPI backend foundation for Thinkloop AI Socratic tutoring platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)

    # Centralized exception handlers
    setup_exception_handlers(app)

    # Route registrations
    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(preferences_router)
    app.include_router(concepts_router)
    app.include_router(sessions_router)
    app.include_router(mastery_router)
    app.include_router(streak_router)

    return app


# Default ASGI application instance for Uvicorn
app = create_app()
