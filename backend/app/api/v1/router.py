from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import candidates, dashboard, earnings, explain, export, scan, settings, trades, universe, ws

api_router = APIRouter()

api_router.include_router(earnings.router)
api_router.include_router(scan.router)
api_router.include_router(candidates.router)
api_router.include_router(trades.router)
api_router.include_router(explain.router)
api_router.include_router(universe.router)
api_router.include_router(settings.router)
api_router.include_router(dashboard.router)
api_router.include_router(export.router)
api_router.include_router(ws.router)
