"""Unit tests for structured logging and request_id propagation."""

import json
import logging
import sys

from app.logging import (
    RequestIdFilter,
    StructuredJsonFormatter,
    configure_logging,
    get_request_id,
    set_request_id,
)


def test_structured_json_formatter_includes_request_id() -> None:
    """Formatter outputs valid JSON containing timestamp, level, message, and request_id."""
    set_request_id("test-req-uuid-1234")
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test log message",
        args=(),
        exc_info=None,
    )
    filter_ = RequestIdFilter()
    filter_.filter(record)

    formatter = StructuredJsonFormatter()
    output = formatter.format(record)

    data = json.loads(output)
    assert data["message"] == "Test log message"
    assert data["level"] == "INFO"
    assert data["request_id"] == "test-req-uuid-1234"
    assert "timestamp" in data


def test_request_id_filter_fallback() -> None:
    """When no request_id is bound in context, fallback to empty string or default."""
    set_request_id(None)
    assert get_request_id() is None
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Fallback message",
        args=(),
        exc_info=None,
    )
    filter_ = RequestIdFilter()
    filter_.filter(record)
    assert hasattr(record, "request_id")
    assert record.request_id == ""


def test_structured_json_formatter_with_exception() -> None:
    """Formatter captures exception trace when exc_info is present."""
    try:
        raise ValueError("Something went wrong")
    except ValueError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test_logger",
        level=logging.ERROR,
        pathname="test.py",
        lineno=25,
        msg="Error occurred",
        args=(),
        exc_info=exc_info,
    )
    formatter = StructuredJsonFormatter()
    output = formatter.format(record)
    data = json.loads(output)
    assert "exception" in data
    assert "ValueError: Something went wrong" in data["exception"]


def test_configure_logging() -> None:
    """configure_logging sets up root logger with StructuredJsonFormatter and RequestIdFilter."""
    configure_logging("DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) > 0
    assert isinstance(root.handlers[0].formatter, StructuredJsonFormatter)
