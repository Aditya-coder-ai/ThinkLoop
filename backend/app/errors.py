"""Application error hierarchy and centralized exception handlers."""

import logging
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging import get_request_id
from app.schemas.error import ErrorDetail, ErrorEnvelope

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base domain error for Thinkloop application exceptions."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = 500,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.headers = headers or {}


class AuthenticationError(AppError):
    """Raised when authentication credentials are missing, invalid, or expired."""

    def __init__(
        self,
        message: str = "Could not validate authentication credentials",
        code: str = "UNAUTHORIZED",
        headers: dict[str, str] | None = None,
    ) -> None:
        default_headers = {"WWW-Authenticate": "Bearer"}
        if headers:
            default_headers.update(headers)
        super().__init__(message=message, code=code, status_code=401, headers=default_headers)


class NotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "NOT_FOUND",
    ) -> None:
        super().__init__(message=message, code=code, status_code=404)


class ConflictError(AppError):
    """Raised when an operation conflicts with the current resource state."""

    def __init__(
        self,
        message: str = "Resource conflict",
        code: str = "CONFLICT",
    ) -> None:
        super().__init__(message=message, code=code, status_code=409)


class RateLimitExceededError(AppError):
    """Raised when client exceeds rate limit quotas."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please retry later.",
        code: str = "RATE_LIMIT_EXCEEDED",
        retry_after: int = 60,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )


class ValidationError(AppError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str = "Invalid request payload or parameters",
        code: str = "VALIDATION_ERROR",
    ) -> None:
        super().__init__(message=message, code=code, status_code=422)


class InternalServerError(AppError):
    """Raised when an unrecoverable internal server error occurs."""

    def __init__(
        self,
        message: str = "An unexpected error occurred. Please try again later.",
        code: str = "INTERNAL_SERVER_ERROR",
    ) -> None:
        super().__init__(message=message, code=code, status_code=500)


def create_error_response(
    status_code: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Format standard ErrorEnvelope JSON response."""
    request_id = get_request_id() or ""
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=request_id,
        )
    )
    resp_headers = dict(headers or {})
    if request_id and "X-Request-ID" not in resp_headers:
        resp_headers["X-Request-ID"] = request_id

    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(),
        headers=resp_headers,
    )


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """Handle domain AppError instances."""
    return create_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        headers=exc.headers,
    )


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle Starlette and FastAPI HTTPExceptions."""
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_SERVER_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
    message = str(exc.detail) if exc.detail else "An HTTP error occurred"
    return create_error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=exc.headers,
    )


async def validation_exception_handler(
    _request: Request, _exc: RequestValidationError
) -> JSONResponse:
    """Handle FastAPI request validation errors (422)."""
    return create_error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
    )


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler ensuring no tracebacks or internal details leak to clients."""
    logger.exception("Unhandled application exception: %s", exc)
    return create_error_response(
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected internal server error occurred",
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register all centralized exception handlers on the FastAPI application."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
