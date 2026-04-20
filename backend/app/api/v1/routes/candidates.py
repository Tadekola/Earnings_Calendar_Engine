from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RecommendationClass
from app.core.errors import raise_not_found
from app.db.session import get_db
from app.models.scan import ScanResult
from app.schemas.scan import ScanResultResponse

router = APIRouter(prefix="/candidates", tags=["candidates"])


class IVPoint(BaseModel):
    expiration: date
    days_to_expiry: int
    atm_iv: float
    call_iv: float | None = None
    put_iv: float | None = None


class IVTermStructureResponse(BaseModel):
    ticker: str
    spot_price: float
    points: list[IVPoint]


@router.get("/{ticker}/iv-term-structure", response_model=IVTermStructureResponse)
async def get_iv_term_structure(request: Request, ticker: str) -> IVTermStructureResponse:
    """Return ATM implied volatility for each available expiration — powers the IV term structure chart."""
    ticker = ticker.upper()
    registry = request.app.state.provider_registry
    chain = await registry.options.get_options_chain(ticker)

    if not chain or not chain.options:
        raise_not_found("Options chain", ticker)

    spot = chain.spot_price
    today = date.today()
    points: list[IVPoint] = []

    for exp in sorted(chain.expirations):
        dte = (exp - today).days
        if dte < 1:
            continue

        exp_opts = [o for o in chain.options if o.expiration == exp and o.implied_volatility]
        if not exp_opts:
            continue

        # Find ATM strike (closest to spot)
        atm_strike = min({o.strike for o in exp_opts}, key=lambda s: abs(s - spot))

        atm_calls = [o for o in exp_opts if o.strike == atm_strike and o.option_type == "call"]
        atm_puts = [o for o in exp_opts if o.strike == atm_strike and o.option_type == "put"]

        call_iv = atm_calls[0].implied_volatility if atm_calls else None
        put_iv = atm_puts[0].implied_volatility if atm_puts else None

        ivs = [v for v in [call_iv, put_iv] if v is not None and v > 0]
        if not ivs:
            continue

        atm_iv = sum(ivs) / len(ivs)
        points.append(IVPoint(
            expiration=exp,
            days_to_expiry=dte,
            atm_iv=round(atm_iv * 100, 2),
            call_iv=round(call_iv * 100, 2) if call_iv else None,
            put_iv=round(put_iv * 100, 2) if put_iv else None,
        ))

    return IVTermStructureResponse(ticker=ticker, spot_price=spot, points=points)


@router.get("/{ticker}", response_model=ScanResultResponse)
async def get_candidate(
    request: Request,
    ticker: str,
    db: AsyncSession = Depends(get_db),
) -> ScanResultResponse:
    """Return the ticker's most recent scan result (classification, score,
    strategy, rationale). The UI renders this on the candidate detail page.

    Falls back to a live provider probe only when the ticker has never been
    scanned.
    """
    ticker = ticker.upper()
    settings = request.app.state.settings
    registry = request.app.state.provider_registry

    if ticker not in settings.DEFAULT_UNIVERSE:
        raise_not_found("Candidate", ticker)

    # Pull the most recent scan result for this ticker
    row = (
        await db.execute(
            select(ScanResult)
            .where(ScanResult.ticker == ticker)
            .order_by(ScanResult.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is not None:
        rejections: list[str] | None = None
        if row.rejection_reasons:
            rejections = [r.strip() for r in row.rejection_reasons.split(";") if r.strip()]
        return ScanResultResponse(
            ticker=row.ticker,
            classification=RecommendationClass(row.classification),
            overall_score=row.overall_score,
            stage_reached=row.stage_reached,
            rejection_reasons=rejections,
            rationale_summary=row.rationale_summary,
            strategy_type=row.strategy_type,
            layer_id=row.layer_id,
            account_id=row.account_id,
            processing_time_ms=row.processing_time_ms,
        )

    # No prior scan — return a minimal live snapshot so the UI still loads
    earnings_rec = await registry.earnings.get_earnings_date(ticker)
    vol_snap = await registry.volatility.get_volatility_metrics(ticker)
    price_rec = await registry.price.get_current_price(ticker)

    if earnings_rec:
        days_to = (earnings_rec.earnings_date - date.today()).days
        earnings_info = f"Earnings in {days_to} days ({earnings_rec.confidence})"
    else:
        earnings_info = "No earnings (index)" if ticker == "XSP" else "No earnings date"

    spot_str = f"${price_rec.close:.2f}" if price_rec else "N/A"
    ivr = vol_snap.iv_rank
    slope = vol_snap.term_structure_slope
    return ScanResultResponse(
        ticker=ticker,
        classification=RecommendationClass.NO_TRADE,
        overall_score=None,
        stage_reached="NO_PRIOR_SCAN",
        rationale_summary=(
            f"{ticker}: Spot {spot_str}. {earnings_info}. "
            f"IV Rank: {ivr:.2f}. Term slope: {slope:.3f}. "
            f"Run a scan for full scoring."
            if ivr is not None and slope is not None
            else f"{ticker}: Spot {spot_str}. {earnings_info}. Run a scan for full scoring."
        ),
    )
