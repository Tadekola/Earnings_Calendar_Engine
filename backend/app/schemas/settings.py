from __future__ import annotations

from pydantic import BaseModel

from app.core.enums import OperatingMode, UniverseSource


class ScoringSettingsResponse(BaseModel):
    liquidity_weight: float
    earnings_timing_weight: float
    vol_term_structure_weight: float
    containment_weight: float
    pricing_efficiency_weight: float
    event_cleanliness_weight: float
    historical_fit_weight: float
    recommend_threshold: float
    watchlist_threshold: float
    scoring_version: str


class LiquiditySettingsResponse(BaseModel):
    min_avg_stock_volume: int
    min_avg_option_volume: int
    min_open_interest: int
    max_bid_ask_pct: float
    max_bid_ask_abs: float
    max_spread_to_mid: float
    min_strike_density: int


class EarningsWindowSettingsResponse(BaseModel):
    min_days_to_earnings: int
    max_days_to_earnings: int
    exit_days_before_earnings: int
    require_confirmed_date: bool


class AppSettingsResponse(BaseModel):
    operating_mode: OperatingMode
    universe_source: UniverseSource
    scoring: ScoringSettingsResponse
    liquidity: LiquiditySettingsResponse
    earnings_window: EarningsWindowSettingsResponse
    universe_tickers: list[str]


class AppSettingsUpdateRequest(BaseModel):
    operating_mode: OperatingMode | None = None
    universe_source: UniverseSource | None = None
    recommend_threshold: float | None = None
    watchlist_threshold: float | None = None
    min_days_to_earnings: int | None = None
    max_days_to_earnings: int | None = None
    exit_days_before_earnings: int | None = None
    min_avg_stock_volume: int | None = None
    min_avg_option_volume: int | None = None
    universe_tickers: list[str] | None = None
