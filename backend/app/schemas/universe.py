from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UniverseTickerResponse(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    avg_daily_volume: float | None = None
    avg_option_volume: float | None = None
    is_active: bool = True


class UniverseResponse(BaseModel):
    total: int
    active: int
    tickers: list[UniverseTickerResponse]
