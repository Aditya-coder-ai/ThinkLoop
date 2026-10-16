"""Uniform error response schemas."""

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error object returned within error envelope."""

    code: str = Field(..., description="Machine-readable error classification code")
    message: str = Field(..., description="Human-readable error description")
    request_id: str = Field(..., description="Unique request tracing identifier")


class ErrorEnvelope(BaseModel):
    """Standardized root error envelope for all client-facing API errors."""

    error: ErrorDetail
