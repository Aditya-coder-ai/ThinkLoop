"""Unit tests for AppError hierarchy, response generators, and error handlers."""

from unittest.mock import MagicMock

import pytest
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import (
    AppError,
    AuthenticationError,
    InternalServerError,
    NotFoundError,
    RateLimitExceededError,
    app_error_handler,
    create_error_response,
    http_exception_handler,
    setup_exception_handlers,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.errors import (
    ValidationError as AppValidationError,
)
from app.logging import set_request_id


def test_app_error_hierarchy() -> None:
    """All custom application errors inherit from AppError."""
    assert issubclass(AuthenticationError, AppError)
    assert issubclass(NotFoundError, AppError)
    assert issubclass(RateLimitExceededError, AppError)
    assert issubclass(AppValidationError, AppError)
    assert issubclass(InternalServerError, AppError)


def test_app_error_attributes() -> None:
    """AppError encapsulates code, status_code, message, and headers."""
    err = RateLimitExceededError(
        message="Too many requests",
        retry_after=60,
    )
    assert err.code == "RATE_LIMIT_EXCEEDED"
    assert err.status_code == 429
    assert err.message == "Too many requests"
    assert err.headers is not None
    assert err.headers.get("Retry-After") == "60"

    auth_err = AuthenticationError(headers={"X-Custom": "val"})
    assert auth_err.status_code == 401
    assert auth_err.headers.get("X-Custom") == "val"
    assert "WWW-Authenticate" in auth_err.headers

    nf_err = NotFoundError("Item not found")
    assert nf_err.status_code == 404
    assert nf_err.code == "NOT_FOUND"

    val_err = AppValidationError("Invalid data")
    assert val_err.status_code == 422
    assert val_err.code == "VALIDATION_ERROR"

    int_err = InternalServerError("Crash")
    assert int_err.status_code == 500
    assert int_err.code == "INTERNAL_SERVER_ERROR"


def test_create_error_response_with_request_id() -> None:
    """create_error_response populates request_id and X-Request-ID header."""
    set_request_id("unit-test-req-id")
    response = create_error_response(
        status_code=400,
        code="BAD_REQUEST",
        message="Invalid parameters",
    )
    assert response.status_code == 400
    assert response.headers["X-Request-ID"] == "unit-test-req-id"
    import json

    data = json.loads(response.body.decode())
    assert data["error"]["code"] == "BAD_REQUEST"
    assert data["error"]["request_id"] == "unit-test-req-id"


@pytest.mark.asyncio
async def test_error_handlers() -> None:
    """All error handlers return expected JSONResponse shapes."""
    set_request_id("handler-test-req")
    req = MagicMock()

    # app_error_handler
    app_err = NotFoundError("Missing item")
    res1 = await app_error_handler(req, app_err)
    assert res1.status_code == 404

    # http_exception_handler
    http_err = StarletteHTTPException(status_code=403, detail="Forbidden area")
    res2 = await http_exception_handler(req, http_err)
    assert res2.status_code == 403

    # validation_exception_handler
    val_err = RequestValidationError(errors=[])
    res3 = await validation_exception_handler(req, val_err)
    assert res3.status_code == 422

    # unhandled_exception_handler
    exc = RuntimeError("Database crash!")
    res4 = await unhandled_exception_handler(req, exc)
    assert res4.status_code == 500

    # setup_exception_handlers
    app_mock = MagicMock()
    setup_exception_handlers(app_mock)
    assert app_mock.add_exception_handler.call_count == 4
