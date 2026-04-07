from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RecommendedTrade(Base):
    __tablename__ = "recommended_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    spot_price: Mapped[float] = mapped_column(Float, nullable=False)
    earnings_date: Mapped[date] = mapped_column(Date, nullable=False)
    earnings_confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_date_start: Mapped[date] = mapped_column(Date, nullable=False)
    entry_date_end: Mapped[date] = mapped_column(Date, nullable=False)
    planned_exit_date: Mapped[date] = mapped_column(Date, nullable=False)
    short_expiry: Mapped[date] = mapped_column(Date, nullable=False)
    long_expiry: Mapped[date] = mapped_column(Date, nullable=False)
    lower_strike: Mapped[float] = mapped_column(Float, nullable=False)
    upper_strike: Mapped[float] = mapped_column(Float, nullable=False)
    total_debit_mid: Mapped[float] = mapped_column(Float, nullable=False)
    total_debit_pessimistic: Mapped[float | None] = mapped_column(Float)
    estimated_max_loss: Mapped[float] = mapped_column(Float, nullable=False)
    profit_zone_low: Mapped[float | None] = mapped_column(Float)
    profit_zone_high: Mapped[float | None] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    rationale_summary: Mapped[str | None] = mapped_column(Text)
    key_risks: Mapped[str | None] = mapped_column(Text)
    risk_disclaimer: Mapped[str | None] = mapped_column(Text)
    construction_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TradeLeg(Base):
    __tablename__ = "trade_legs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    leg_number: Mapped[int] = mapped_column(Integer, nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    expiration: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    bid: Mapped[float | None] = mapped_column(Float)
    ask: Mapped[float | None] = mapped_column(Float)
    mid: Mapped[float | None] = mapped_column(Float)
    implied_volatility: Mapped[float | None] = mapped_column(Float)
    delta: Mapped[float | None] = mapped_column(Float)
    theta: Mapped[float | None] = mapped_column(Float)
    vega: Mapped[float | None] = mapped_column(Float)
    open_interest: Mapped[int | None] = mapped_column(Integer)
    volume: Mapped[int | None] = mapped_column(Integer)
    spread_to_mid: Mapped[float | None] = mapped_column(Float)
