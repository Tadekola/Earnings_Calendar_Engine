from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RecommendationClass
from app.db.session import get_db
from app.models.scan import ScanResult
from app.schemas.explain import (
    ExplainFactorResponse,
    ExplainResponse,
    RejectionResponse,
    RejectionsListResponse,
)
from app.services._price_fallback import get_tradier_fallback_price
from app.services.liquidity import LiquidityEngine

router = APIRouter(tags=["explain"])


@router.get("/explain/{ticker}", response_model=ExplainResponse)
async def explain_ticker(
    request: Request,
    ticker: str,
    strategy: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ExplainResponse:
    ticker = ticker.upper()
    registry = request.app.state.provider_registry
    settings = request.app.state.settings

    # Prefer the latest persisted scan classification so the header matches
    # what the scan decided. Falls through to live-compute when no prior
    # scan exists for this ticker.
    db_row = (
        await db.execute(
            select(ScanResult)
            .where(ScanResult.ticker == ticker)
            .order_by(ScanResult.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    earnings_rec = await registry.earnings.get_earnings_date(ticker)
    vol_snap = await registry.volatility.get_volatility_metrics(ticker)
    price_rec = await registry.price.get_current_price(ticker)
    if price_rec is None:
        price_rec = await get_tradier_fallback_price(registry, ticker)
    chain = await registry.options.get_options_chain(ticker)

    factors: list[ExplainFactorResponse] = []
    risk_warnings: list[str] = []
    data_notes: list[str] = []
    rejection_reasons: list[str] = []

    # XSP (and future index products) has no earnings date by design — it
    # scores on its own iron-butterfly path. Only treat missing earnings as
    # disqualifying for real equities.
    if not earnings_rec and ticker != "XSP":
        rejection_reasons.append("No earnings date found")
        db_cls = RecommendationClass(db_row.classification) if db_row else RecommendationClass.NO_TRADE
        db_score = db_row.overall_score if db_row and db_row.overall_score is not None else 0.0
        return ExplainResponse(
            ticker=ticker,
            classification=db_cls,
            overall_score=db_score,
            summary=f"{ticker}: No upcoming earnings — not eligible.",
            factors=[],
            rejection_reasons=rejection_reasons,
            risk_warnings=["Options trading involves significant risk of loss."],
            data_quality_notes=[],
            recommendation_rationale=(
                db_row.rationale_summary
                if db_row and db_row.rationale_summary
                else f"{ticker} has no upcoming earnings date."
            ),
        )

    # Run real scoring engine via the requested strategy or default Double Calendar
    from app.services.base_strategy import StrategyFactory

    factory = StrategyFactory(settings, registry)
    active_strats = factory.get_active_strategies()
    strat = (
        next(
            (s for s in active_strats if s.strategy_type.upper() == strategy.upper()),
            active_strats[0],
        )
        if strategy
        else active_strats[0]
    )

    # Since explain doesn't build the trade, we have to determine expirations
    # Let's temporarily build the trade to get expirations and full evaluation
    try:
        strat = next(
            s for s in active_strats if s.strategy_type.upper() == strat.strategy_type.upper()
        )
        trade = strat.build_trade_structure(
            ticker, earnings_rec, price_rec or _default_price(ticker), vol_snap, chain
        )
        front_exp = trade.short_expiry
        long_exp = trade.long_expiry
    except Exception:
        # Fallback expirations
        from app.services.scan_pipeline import ScanPipeline

        pipeline = ScanPipeline(settings, registry)
        days_to = (
            (earnings_rec.earnings_date - __import__("datetime").date.today()).days
            if earnings_rec
            else 0
        )
        front_exp_opt, long_exp_opt = pipeline._select_expirations(
            chain,
            earnings_rec,
            days_to,
        )
        front_exp = front_exp_opt or __import__("datetime").date.today()
        long_exp = long_exp_opt or __import__("datetime").date.today()

    liq_engine = LiquidityEngine(settings.liquidity)
    if price_rec and chain.expirations and front_exp and long_exp:
        full_liq = strat.validate_liquidity(price_rec, chain, front_exp, long_exp)
    elif price_rec:
        full_liq = liq_engine.evaluate_stock_liquidity(price_rec)
    else:
        from app.services.liquidity import LiquidityCheckResult

        full_liq = LiquidityCheckResult(
            passed=False, score=0.0, rejection_reasons=["No price data"]
        )

    scoring_result = strat.calculate_score(
        ticker=ticker,
        earnings=earnings_rec,
        price=price_rec or _default_price(ticker),
        vol=vol_snap,
        chain=chain,
        liquidity=full_liq,
    )

    for f in scoring_result.factors:
        factors.append(
            ExplainFactorResponse(
                factor=f.name,
                score=f.raw_score,
                weight=f.weight,
                weighted_contribution=f.weighted_score,
                explanation=f.rationale,
            )
        )

    risk_warnings = scoring_result.risk_warnings
    if earnings_rec and earnings_rec.meta.source_name == "mock_earnings":
        data_notes.append("Using mock earnings data — verify with live sources.")
    if vol_snap.meta.source_name == "mock_volatility":
        data_notes.append("Using mock volatility data — verify with live sources.")

    # Prefer the DB's classification/score over a freshly-recomputed one so
    # the header on the candidate page matches exactly what the scan
    # decided (avoids micro-variance from intraday price moves).
    final_cls = (
        RecommendationClass(db_row.classification) if db_row else scoring_result.classification
    )
    final_score = (
        db_row.overall_score
        if db_row and db_row.overall_score is not None
        else scoring_result.overall_score
    )
    final_rationale = (
        db_row.rationale_summary
        if db_row and db_row.rationale_summary
        else scoring_result.rationale_summary
    )

    return ExplainResponse(
        ticker=ticker,
        classification=final_cls,
        overall_score=final_score,
        summary=(
            f"{ticker} analysis: {len(factors)} factors evaluated."
            f" Score: {final_score}."
        ),
        factors=factors,
        rejection_reasons=rejection_reasons,
        risk_warnings=risk_warnings,
        data_quality_notes=data_notes,
        recommendation_rationale=final_rationale,
    )


def _default_price(ticker: str):
    from datetime import date

    from app.providers.base import PriceRecord

    return PriceRecord(
        ticker=ticker, trade_date=date.today(), open=0, high=0, low=0, close=0, volume=0
    )


# Shared scan store — import from scan route
from app.api.v1.routes.scan import _scan_store  # noqa: E402


@router.get("/rejections", response_model=RejectionsListResponse)
async def get_rejections() -> RejectionsListResponse:
    if not _scan_store:
        return RejectionsListResponse(total=0, scan_run_id=None, rejections=[])

    latest_run = list(_scan_store.values())[-1]
    rejections = []
    for r in latest_run.results:
        if r.classification == RecommendationClass.NO_TRADE:
            reasons = r.rejection_reasons or []
            rejections.append(
                RejectionResponse(
                    ticker=r.ticker,
                    stage=r.stage_reached,
                    reason="; ".join(reasons) if reasons else "Score below threshold",
                    details=r.rationale_summary or None,
                )
            )

    return RejectionsListResponse(
        total=len(rejections),
        scan_run_id=latest_run.run_id,
        rejections=rejections,
    )
