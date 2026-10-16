"""FastAPI application factory and lifecycle management."""

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.health import router as health_router
from app.api.me import router as me_router
from app.config import Settings, get_settings
from app.core.security import JWKSService
from app.db.session import create_engine, create_session_factory
from app.errors import setup_exception_handlers
from app.logging import configure_logging, set_request_id


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

        yield

        # Shutdown
        await redis_client.close()
        await engine.dispose()

    app = FastAPI(
        title="Thinkloop API",
        description="FastAPI backend foundation for Thinkloop AI Socratic tutoring platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(RequestIdMiddleware)

    # Centralized exception handlers
    setup_exception_handlers(app)

    # Route registrations
    app.include_router(health_router)
    app.include_router(me_router)

    return app


# Default ASGI application instance for Uvicorn
app = create_app()
