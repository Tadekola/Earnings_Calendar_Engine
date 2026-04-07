"""WebSocket endpoint for real-time scan progress."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws_manager import scan_ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/scan")
async def scan_progress_ws(ws: WebSocket) -> None:
    """WebSocket that streams scan progress events to connected clients."""
    await scan_ws_manager.connect(ws)
    try:
        # Keep connection alive — wait for client to disconnect
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await scan_ws_manager.disconnect(ws)
