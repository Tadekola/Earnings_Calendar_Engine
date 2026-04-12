from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from app.core.enums import RecommendationClass
from app.core.errors import raise_not_found
from app.schemas.scan import ScanResultResponse

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("/{ticker}", response_model=ScanResultResponse)
async def get_candidate(request: Request, ticker: str) -> ScanResultResponse:
    ticker = ticker.upper()
    registry = request.app.state.provider_registry
    settings = request.app.state.settings

    if ticker not in settings.DEFAULT_UNIVERSE:
        raise_not_found("Candidate", ticker)

    earnings_rec = await registry.earnings.get_earnings_date(ticker)
    if earnings_rec is None and ticker != "XSP":
        raise_not_found("Earnings data for candidate", ticker)

    vol_snap = await registry.volatility.get_volatility_metrics(ticker)
    price_rec = await registry.price.get_current_price(ticker)

    if earnings_rec:
        days_to = (earnings_rec.earnings_date - date.today()).days
        earnings_info = (
            f"Earnings in {days_to} days"
            f" ({earnings_rec.confidence})"
        )
    else:
        days_to = 0
        earnings_info = "No earnings (index)"

    return ScanResultResponse(
        ticker=ticker,
        classification=RecommendationClass.NO_TRADE,
        overall_score=None,
        stage_reached="CANDIDATE_LOOKUP",
        rationale_summary=(
            f"{ticker}: Spot"
            f" {f'${price_rec.close:.2f}' if price_rec else 'N/A'}. "
            f"{earnings_info}. "
            f"IV Rank:"
            f" {vol_snap.iv_rank if vol_snap.iv_rank else 'N/A'}. "
            f"Term structure slope: "
            f"{vol_snap.term_structure_slope if vol_snap.term_structure_slope else 'N/A'}. "
            f"Run a scan for full scoring."
        ),
    )
