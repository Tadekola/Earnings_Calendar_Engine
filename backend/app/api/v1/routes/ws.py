"""WebSocket endpoint for real-time scan progress."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws_manager import scan_ws_manager

router = APIRouter(tags=["websocket"])

# Seconds between keepalive pings when the client is idle.
_WS_KEEPALIVE_SECONDS = 20


@router.websocket("/ws/scan")
async def scan_progress_ws(ws: WebSocket) -> None:
    """WebSocket that streams scan progress events to connected clients."""
    await scan_ws_manager.connect(ws)
    try:
        # Keep connection alive with periodic pings while waiting for the
        # client to disconnect. This prevents idle proxies/load balancers from
        # closing the socket during long scans.
        while True:
            try:
                await asyncio.wait_for(
                    ws.receive_text(), timeout=_WS_KEEPALIVE_SECONDS
                )
            except TimeoutError:
                await ws.send_text('{"type":"ping"}')
    except WebSocketDisconnect:
        pass
    finally:
        await scan_ws_manager.disconnect(ws)
