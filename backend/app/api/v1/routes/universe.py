from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.universe import UniverseResponse, UniverseTickerResponse

router = APIRouter(prefix="/universe", tags=["universe"])


@router.get("", response_model=UniverseResponse)
async def get_universe(request: Request) -> UniverseResponse:
    settings = request.app.state.settings
    tickers = [
        UniverseTickerResponse(
            ticker=t,
            is_active=True,
        )
        for t in settings.DEFAULT_UNIVERSE
    ]
    return UniverseResponse(
        total=len(tickers),
        active=len(tickers),
        tickers=tickers,
    )
