from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)


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
