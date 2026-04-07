from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.core.enums import EarningsConfidence, ReportTiming


class EarningsEventResponse(BaseModel):
    ticker: str
    earnings_date: date
    report_timing: ReportTiming = ReportTiming.UNKNOWN
    confidence: EarningsConfidence = EarningsConfidence.ESTIMATED
    source: str
    source_confidence: float
    fiscal_quarter: str | None = None
    fiscal_year: int | None = None
    days_until_earnings: int
    last_updated: datetime | None = None


class UpcomingEarningsResponse(BaseModel):
    total: int
    window_start: date
    window_end: date
    earnings: list[EarningsEventResponse]
