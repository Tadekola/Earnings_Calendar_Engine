from __future__ import annotations

from secrets import compare_digest

from fastapi import Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def require_api_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if not settings.API_AUTH_REQUIRED:
        return

    expected = settings.ECE_API_KEY
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is required but ECE_API_KEY is not configured",
        )

    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()

    supplied = x_api_key or bearer
    if supplied is None or not compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid API key required",
        )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "unknown",
        )
        try:
            response = await call_next(request)
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
            )
            return response
        except Exception as exc:
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(exc),
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )


RISK_DISCLAIMER = (
    "This application is for educational and decision-support purposes only. "
    "It does not guarantee profits. Recommendation quality depends on data quality. "
    "Earnings dates can change without notice. Users must verify execution prices independently. "
    "This application does not promise actual fills or trade execution. "
    "Options trading involves significant risk of loss."
)
