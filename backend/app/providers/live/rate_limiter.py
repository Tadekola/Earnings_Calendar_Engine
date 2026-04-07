"""Async token-bucket rate limiter for API providers."""
from __future__ import annotations

import asyncio
import time

from app.core.logging import get_logger

logger = get_logger(__name__)


class AsyncRateLimiter:
    """Token-bucket rate limiter.

    Args:
        requests_per_minute: Max requests allowed per minute.
        name: Label for logging.
    """

    def __init__(self, requests_per_minute: int, name: str = "rate_limiter") -> None:
        self._rate = requests_per_minute / 60.0  # tokens per second
        self._max_tokens = float(requests_per_minute)
        self._tokens = float(requests_per_minute)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()
        self._name = name

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max_tokens, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def acquire(self) -> None:
        """Wait until a request token is available."""
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            # Calculate wait time for next token
            wait = (1.0 - self._tokens) / self._rate
            logger.debug("rate_limit_wait", limiter=self._name, wait_seconds=round(wait, 3))

        await asyncio.sleep(wait)

        async with self._lock:
            self._refill()
            self._tokens = max(0.0, self._tokens - 1.0)
