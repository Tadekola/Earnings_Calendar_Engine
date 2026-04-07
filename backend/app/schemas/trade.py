from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.core.enums import LegSide, OptionType, RecommendationClass


class TradeLegResponse(BaseModel):
    leg_number: int
    option_type: OptionType
    side: LegSide
    strike: float
    expiration: date
    quantity: int = 1
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    theta: float | None = None
    vega: float | None = None
    open_interest: int | None = None
    volume: int | None = None
    spread_to_mid: float | None = None


class RecommendedTradeResponse(BaseModel):
    ticker: str
    spot_price: float
    earnings_date: date
    earnings_confidence: str
    entry_date_start: date
    entry_date_end: date
    planned_exit_date: date
    short_expiry: date
    long_expiry: date
    lower_strike: float
    upper_strike: float
    total_debit_mid: float
    total_debit_pessimistic: float | None = None
    estimated_max_loss: float
    profit_zone_low: float | None = None
    profit_zone_high: float | None = None
    classification: RecommendationClass
    overall_score: float
    rationale_summary: str | None = None
    key_risks: list[str] = []
    risk_disclaimer: str
    legs: list[TradeLegResponse] = []


class TradeBuildRequest(BaseModel):
    ticker: str
    lower_strike: float | None = None
    upper_strike: float | None = None
    short_expiry: date | None = None
    long_expiry: date | None = None
    symmetric: bool = True


class TradeRepriceRequest(BaseModel):
    ticker: str
    lower_strike: float
    upper_strike: float
    short_expiry: date
    long_expiry: date
