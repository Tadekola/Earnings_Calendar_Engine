from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Backtest(Base):
    """A backtesting run — evaluates historical trade recommendations."""

    __tablename__ = "backtests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backtest_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    # Config
    strategy_filter: Mapped[str | None] = mapped_column(String(50))  # DOUBLE_CALENDAR, IRON_BUTTERFLY_ATM, etc.
    min_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    # Results summary
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    avg_pnl_per_trade: Mapped[float | None] = mapped_column(Float)
    win_rate: Mapped[float | None] = mapped_column(Float)
    avg_hold_days: Mapped[float | None] = mapped_column(Float)
    max_drawdown: Mapped[float | None] = mapped_column(Float)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float)
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class BacktestTrade(Base):
    """Individual trade outcome within a backtest."""

    __tablename__ = "backtest_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backtest_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    scan_run_id: Mapped[str | None] = mapped_column(String(36))
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    layer_id: Mapped[str | None] = mapped_column(String(10))
    account_id: Mapped[str | None] = mapped_column(String(50))
    # Entry
    entry_score: Mapped[float] = mapped_column(Float, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_spot: Mapped[float] = mapped_column(Float, nullable=False)
    entry_debit: Mapped[float] = mapped_column(Float, nullable=False)
    entry_iv: Mapped[float | None] = mapped_column(Float)
    # Exit
    exit_date: Mapped[date | None] = mapped_column(Date)
    exit_spot: Mapped[float | None] = mapped_column(Float)
    exit_credit: Mapped[float | None] = mapped_column(Float)
    exit_iv: Mapped[float | None] = mapped_column(Float)
    exit_reason: Mapped[str | None] = mapped_column(String(50))  # PLANNED, EARNINGS_HIT, STOP_LOSS, EXPIRED
    # Earnings
    earnings_date: Mapped[date | None] = mapped_column(Date)
    earnings_move_pct: Mapped[float | None] = mapped_column(Float)
    # P&L
    realized_pnl: Mapped[float | None] = mapped_column(Float)
    realized_pnl_pct: Mapped[float | None] = mapped_column(Float)
    hold_days: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str | None] = mapped_column(String(20))  # WIN, LOSS, BREAKEVEN
    # Structure reference
    lower_strike: Mapped[float | None] = mapped_column(Float)
    upper_strike: Mapped[float | None] = mapped_column(Float)
    short_expiry: Mapped[date | None] = mapped_column(Date)
    long_expiry: Mapped[date | None] = mapped_column(Date)
    # Meta
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
