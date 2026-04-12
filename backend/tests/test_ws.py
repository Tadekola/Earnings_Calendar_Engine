"""Tests for WebSocket connection manager."""

from __future__ import annotations

import pytest

from app.services.ws_manager import ConnectionManager


@pytest.mark.asyncio
async def test_broadcast_no_connections():
    """Broadcast with no connections should not raise."""
    mgr = ConnectionManager()
    await mgr.broadcast({"type": "test"})


@pytest.mark.asyncio
async def test_progress_callback_type():
    """Manager.broadcast matches the ProgressCallback signature."""
    from app.services.scan_pipeline import ProgressCallback

    mgr = ConnectionManager()
    cb: ProgressCallback = mgr.broadcast
    # Should be callable with dict arg
    await cb({"type": "test", "pct": 50})
