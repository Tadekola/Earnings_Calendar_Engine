from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, Request

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
            fiscal_quarter=r.fiscal_quarter,
            fiscal_year=r.fiscal_year,
            days_until_earnings=(r.earnings_date - today).days,
            last_updated=r.meta.freshness_timestamp,
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
