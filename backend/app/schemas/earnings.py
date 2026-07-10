from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import EarningsConfidence, ReportTiming


class EarningsEventResponse(BaseModel):
    ticker: str
    earnings_date: date
    report_timing: ReportTiming = ReportTiming.UNKNOWN
    confidence: EarningsConfidence = EarningsConfidence.ESTIMATED
    source: str
    source_confidence: float
    is_live_source: bool
    fiscal_quarter: str | None = None
    fiscal_year: int | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None
    estimate_last_updated: datetime | None = None
    days_until_earnings: int
    last_updated: datetime | None = None
    data_quality_notes: list[str] = Field(default_factory=list)


class UpcomingEarningsResponse(BaseModel):
    total: int
    window_start: date
    window_end: date
    earnings: list[EarningsEventResponse]
