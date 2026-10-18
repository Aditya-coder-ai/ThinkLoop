"""Authentication and session lifecycle endpoints."""

import logging

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit(limit=120, window_seconds=60))],
)
async def logout(response: Response) -> Response:
    """Idempotently clear server-side session credentials and cookies."""
    response.delete_cookie(
        key="thinkloop_auth_token",
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
