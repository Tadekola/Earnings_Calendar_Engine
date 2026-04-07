from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EarningsEvent(Base):
    __tablename__ = "earnings_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    earnings_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    report_timing: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="ESTIMATED")
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    fiscal_quarter: Mapped[str | None] = mapped_column(String(10))
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
