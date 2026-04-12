from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class BacktestCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    strategy_filter: str | None = None
    min_score: float = 0.0
    start_date: date | None = None
    end_date: date | None = None


class BacktestTradeResponse(BaseModel):
    id: int
    backtest_id: str
    ticker: str
    strategy_type: str
    layer_id: str | None = None
    account_id: str | None = None
    entry_score: float
    entry_date: date
    entry_spot: float
    entry_debit: float
    entry_iv: float | None = None
    exit_date: date | None = None
    exit_spot: float | None = None
    exit_credit: float | None = None
    exit_iv: float | None = None
    exit_reason: str | None = None
    earnings_date: date | None = None
    earnings_move_pct: float | None = None
    realized_pnl: float | None = None
    realized_pnl_pct: float | None = None
    hold_days: int | None = None
    outcome: str | None = None
    lower_strike: float | None = None
    upper_strike: float | None = None
    notes: str | None = None

    class Config:
        from_attributes = True


class BacktestSummaryResponse(BaseModel):
    backtest_id: str
    name: str
    status: str
    strategy_filter: str | None = None
    min_score: float = 0.0
    start_date: date | None = None
    end_date: date | None = None
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    avg_pnl_per_trade: float | None = None
    win_rate: float | None = None
    avg_hold_days: float | None = None
    max_drawdown: float | None = None
    sharpe_ratio: float | None = None
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None

    class Config:
        from_attributes = True


class BacktestDetailResponse(BacktestSummaryResponse):
    trades: list[BacktestTradeResponse] = []


class BacktestListResponse(BaseModel):
    total: int
    backtests: list[BacktestSummaryResponse]


class PnlCurvePoint(BaseModel):
    trade_index: int
    ticker: str
    cumulative_pnl: float
    trade_pnl: float
    date: date


class BacktestAnalyticsResponse(BaseModel):
    backtest_id: str
    pnl_curve: list[PnlCurvePoint] = []
    by_strategy: dict[str, dict] = {}
    by_layer: dict[str, dict] = {}
    monthly_pnl: dict[str, float] = {}
