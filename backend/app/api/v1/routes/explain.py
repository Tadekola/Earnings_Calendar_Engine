from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.enums import RecommendationClass
from app.core.errors import raise_not_found
from app.schemas.explain import (
    ExplainFactorResponse,
    ExplainResponse,
    RejectionResponse,
    RejectionsListResponse,
)
from app.services.liquidity import LiquidityEngine
from app.services.scoring import ScoringEngine

router = APIRouter(tags=["explain"])


@router.get("/explain/{ticker}", response_model=ExplainResponse)
async def explain_ticker(request: Request, ticker: str) -> ExplainResponse:
    ticker = ticker.upper()
    registry = request.app.state.provider_registry
    settings = request.app.state.settings

    earnings_rec = await registry.earnings.get_earnings_date(ticker)
    vol_snap = await registry.volatility.get_volatility_metrics(ticker)
    price_rec = await registry.price.get_current_price(ticker)
    chain = await registry.options.get_options_chain(ticker)

    factors: list[ExplainFactorResponse] = []
    risk_warnings: list[str] = []
    data_notes: list[str] = []
    rejection_reasons: list[str] = []

    if not earnings_rec:
        rejection_reasons.append("No earnings date found")
        return ExplainResponse(
            ticker=ticker,
            classification=RecommendationClass.NO_TRADE,
            overall_score=0.0,
            summary=f"{ticker}: No upcoming earnings — not eligible.",
            factors=[],
            rejection_reasons=rejection_reasons,
            risk_warnings=["Options trading involves significant risk of loss."],
            data_quality_notes=[],
            recommendation_rationale=f"{ticker} has no upcoming earnings date.",
        )

    # Run real scoring engine
    liq_engine = LiquidityEngine(settings.liquidity)
    scoring_engine = ScoringEngine(settings.scoring, settings.earnings_window)

    if price_rec and chain.expirations:
        from app.services.scan_pipeline import ScanPipeline
        pipeline = ScanPipeline(settings, registry)
        front_exp, back_exp = pipeline._select_expirations(chain, earnings_rec,
            (earnings_rec.earnings_date - __import__("datetime").date.today()).days)
        if front_exp and back_exp:
            full_liq = liq_engine.evaluate_full(price_rec, chain, front_exp, back_exp)
        else:
            full_liq = liq_engine.evaluate_stock_liquidity(price_rec)
    elif price_rec:
        full_liq = liq_engine.evaluate_stock_liquidity(price_rec)
    else:
        from app.services.liquidity import LiquidityCheckResult
        full_liq = LiquidityCheckResult(passed=False, score=0.0, rejection_reasons=["No price data"])

    scoring_result = scoring_engine.score(
        ticker=ticker,
        earnings=earnings_rec,
        price=price_rec or _default_price(ticker),
        vol=vol_snap,
        chain=chain,
        liquidity=full_liq,
    )

    for f in scoring_result.factors:
        factors.append(ExplainFactorResponse(
            factor=f.name,
            score=f.raw_score,
            weight=f.weight,
            weighted_contribution=f.weighted_score,
            explanation=f.rationale,
        ))

    risk_warnings = scoring_result.risk_warnings
    if earnings_rec.meta.source_name == "mock_earnings":
        data_notes.append("Using mock earnings data — verify with live sources.")
    if vol_snap.meta.source_name == "mock_volatility":
        data_notes.append("Using mock volatility data — verify with live sources.")

    return ExplainResponse(
        ticker=ticker,
        classification=scoring_result.classification,
        overall_score=scoring_result.overall_score,
        summary=f"{ticker} analysis: {len(factors)} factors evaluated. Score: {scoring_result.overall_score}.",
        factors=factors,
        rejection_reasons=rejection_reasons,
        risk_warnings=risk_warnings,
        data_quality_notes=data_notes,
        recommendation_rationale=scoring_result.rationale_summary,
    )


def _default_price(ticker: str):
    from datetime import date
    from app.providers.base import PriceRecord
    return PriceRecord(ticker=ticker, trade_date=date.today(), open=0, high=0, low=0, close=0, volume=0)


# Shared scan store — import from scan route
from app.api.v1.routes.scan import _scan_store


@router.get("/rejections", response_model=RejectionsListResponse)
async def get_rejections() -> RejectionsListResponse:
    if not _scan_store:
        return RejectionsListResponse(total=0, scan_run_id=None, rejections=[])

    latest_run = list(_scan_store.values())[-1]
    rejections = []
    for r in latest_run.results:
        if r.classification == RecommendationClass.NO_TRADE:
            reasons = r.rejection_reasons or []
            rejections.append(RejectionResponse(
                ticker=r.ticker,
                stage=r.stage_reached,
                reason="; ".join(reasons) if reasons else "Score below threshold",
                details=r.rationale_summary or None,
            ))

    return RejectionsListResponse(
        total=len(rejections),
        scan_run_id=latest_run.run_id,
        rejections=rejections,
    )
