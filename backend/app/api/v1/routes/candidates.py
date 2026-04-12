from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.enums import RecommendationClass
from app.core.errors import raise_not_found
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
