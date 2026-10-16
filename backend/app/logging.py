"""Structured JSON logging with asynchronous request ID propagation."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# ContextVar storing the current active request ID
_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Retrieve the current request ID from context."""
    return _request_id_ctx.get()


def set_request_id(request_id: str | None) -> None:
    """Set the current request ID in context."""
    _request_id_ctx.set(request_id)


class RequestIdFilter(logging.Filter):
    """Logging filter attaching request_id to LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or ""
        return True


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "") or get_request_id() or "",
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with JSON formatting and request_id filter."""
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredJsonFormatter())
    handler.addFilter(RequestIdFilter())
    root_logger.addHandler(handler)
