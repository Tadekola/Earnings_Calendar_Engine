from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, Request

from app.core.enums import UniverseSource
from app.providers.base import EarningsRecord
from app.providers.live.fmp import FMPEarningsProvider
from app.schemas.earnings import EarningsEventResponse, UpcomingEarningsResponse

router = APIRouter(prefix="/earnings", tags=["earnings"])


@router.get("/upcoming", response_model=UpcomingEarningsResponse)
async def get_upcoming_earnings(
    request: Request,
    days_ahead: int = Query(default=30, ge=1, le=90),
) -> UpcomingEarningsResponse:
    registry = request.app.state.provider_registry
    settings = request.app.state.settings
    tickers = settings.DEFAULT_UNIVERSE
    if (
        settings.data.UNIVERSE_SOURCE == UniverseSource.SP500
        and isinstance(registry.earnings, FMPEarningsProvider)
    ):
        tickers = await registry.earnings.get_sp500_tickers()
        for ticker in settings.DEFAULT_UNIVERSE:
            if ticker == "XSP" and ticker not in tickers:
                tickers.append(ticker)
    today = date.today()

    records = await registry.earnings.get_upcoming_earnings(tickers, days_ahead=days_ahead)

    earnings = [
        EarningsEventResponse(
            ticker=r.ticker,
            earnings_date=r.earnings_date,
            report_timing=r.report_timing,
            confidence=r.confidence,
            source=r.meta.source_name,
            source_confidence=r.meta.confidence_score,
            is_live_source=not r.meta.source_name.startswith("mock_"),
            fiscal_quarter=r.fiscal_quarter,
            fiscal_year=r.fiscal_year,
            eps_estimate=r.eps_estimate,
            eps_actual=r.eps_actual,
            revenue_estimate=r.revenue_estimate,
            revenue_actual=r.revenue_actual,
            estimate_last_updated=r.estimate_last_updated,
            days_until_earnings=(r.earnings_date - today).days,
            last_updated=r.meta.freshness_timestamp,
            data_quality_notes=_data_quality_notes(r),
        )
        for r in records
    ]

    window_end = today
    if earnings:
        window_end = max(e.earnings_date for e in earnings)

    return UpcomingEarningsResponse(
        total=len(earnings),
        window_start=today,
        window_end=window_end,
        earnings=earnings,
    )


def _data_quality_notes(record: EarningsRecord) -> list[str]:
    notes: list[str] = []
    if record.meta.source_name.startswith("mock_"):
        notes.append("Simulated earnings data; do not use for live trading.")
    if record.eps_estimate is None:
        notes.append("EPS consensus estimate unavailable from provider response.")
    if record.revenue_estimate is None:
        notes.append("Revenue consensus estimate unavailable from provider response.")
    if record.confidence != "CONFIRMED":
        notes.append(f"Earnings date confidence is {record.confidence}; verify before entry.")
    return notes
