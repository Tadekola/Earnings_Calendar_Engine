"""Tests for the async rate limiter."""
from __future__ import annotations

import asyncio
import time

import pytest

from app.providers.live.rate_limiter import AsyncRateLimiter


@pytest.mark.asyncio
async def test_immediate_acquire():
    """First acquire should be instant when bucket is full."""
    limiter = AsyncRateLimiter(60, "test")
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


@pytest.mark.asyncio
async def test_burst_within_limit():
    """Multiple acquires within the bucket size should be instant."""
    limiter = AsyncRateLimiter(100, "test")
    start = time.monotonic()
    for _ in range(10):
        await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_rate_limit_throttles():
    """Exceeding the bucket should cause a delay."""
    # 60 req/min = 1 req/sec. Start with 2 tokens.
    limiter = AsyncRateLimiter(2, "test_throttle")
    # Drain both tokens
    await limiter.acquire()
    await limiter.acquire()
    # Third acquire should wait ~60s for a 2/min limiter
    # but we'll just verify it takes more than 0 seconds
    start = time.monotonic()
    # Use a timeout so we don't actually wait 60s
    try:
        await asyncio.wait_for(limiter.acquire(), timeout=0.5)
    except TimeoutError:
        pass
    elapsed = time.monotonic() - start
    # Should have waited (either timed out at 0.5s or waited some time)
    assert elapsed >= 0.3


@pytest.mark.asyncio
async def test_refill_after_wait():
    """Tokens refill over time."""
    limiter = AsyncRateLimiter(600, "test_refill")  # 10/sec
    # Drain 5 tokens
    for _ in range(5):
        await limiter.acquire()
    # Wait a bit for refill
    await asyncio.sleep(0.1)
    # Should be able to acquire again without delay
    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05
