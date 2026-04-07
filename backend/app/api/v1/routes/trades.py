from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.errors import raise_not_found
from app.schemas.trade import (
    RecommendedTradeResponse,
    TradeBuildRequest,
    TradeLegResponse,
    TradeRepriceRequest,
)
from app.services.trade_builder import ConstructedTrade, TradeConstructionEngine

router = APIRouter(prefix="/trades", tags=["trades"])


def _to_response(trade: ConstructedTrade) -> RecommendedTradeResponse:
    legs = [
        TradeLegResponse(
            leg_number=l.leg_number,
            option_type=l.option_type,
            side=l.side,
            strike=l.strike,
            expiration=l.expiration,
            quantity=l.quantity,
            bid=l.bid,
            ask=l.ask,
            mid=l.mid,
            implied_volatility=l.option.implied_volatility if l.option else None,
            delta=l.option.delta if l.option else None,
            theta=l.option.theta if l.option else None,
            vega=l.option.vega if l.option else None,
            open_interest=l.option.open_interest if l.option else None,
            volume=l.option.volume if l.option else None,
            spread_to_mid=l.spread_to_mid,
        )
        for l in trade.legs
    ]
    return RecommendedTradeResponse(
        ticker=trade.ticker,
        spot_price=trade.spot_price,
        earnings_date=trade.earnings_date,
        earnings_confidence=trade.earnings_confidence,
        entry_date_start=trade.entry_date_start,
        entry_date_end=trade.entry_date_end,
        planned_exit_date=trade.planned_exit_date,
        short_expiry=trade.short_expiry,
        long_expiry=trade.long_expiry,
        lower_strike=trade.lower_strike,
        upper_strike=trade.upper_strike,
        total_debit_mid=trade.total_debit_mid,
        total_debit_pessimistic=trade.total_debit_pessimistic,
        estimated_max_loss=trade.estimated_max_loss,
        profit_zone_low=trade.profit_zone_low,
        profit_zone_high=trade.profit_zone_high,
        classification=trade.classification,
        overall_score=trade.overall_score,
        rationale_summary=trade.rationale_summary,
        key_risks=trade.key_risks,
        risk_disclaimer=trade.risk_disclaimer,
        legs=legs,
    )


@router.get("/{ticker}/recommended", response_model=RecommendedTradeResponse)
async def get_recommended_trade(request: Request, ticker: str) -> RecommendedTradeResponse:
    ticker = ticker.upper()
    settings = request.app.state.settings
    registry = request.app.state.provider_registry

    engine = TradeConstructionEngine(settings, registry)
    try:
        trade = await engine.build_recommended(ticker)
    except ValueError as e:
        raise_not_found("Trade", ticker)
    return _to_response(trade)


@router.post("/build", response_model=RecommendedTradeResponse)
async def build_trade(request: Request, body: TradeBuildRequest) -> RecommendedTradeResponse:
    settings = request.app.state.settings
    registry = request.app.state.provider_registry

    engine = TradeConstructionEngine(settings, registry)
    try:
        trade = await engine.build_custom(
            ticker=body.ticker.upper(),
            lower_strike=body.lower_strike,
            upper_strike=body.upper_strike,
            short_expiry=body.short_expiry,
            long_expiry=body.long_expiry,
        )
    except ValueError:
        raise_not_found("Trade", body.ticker)
    return _to_response(trade)


@router.post("/reprice", response_model=RecommendedTradeResponse)
async def reprice_trade(request: Request, body: TradeRepriceRequest) -> RecommendedTradeResponse:
    settings = request.app.state.settings
    registry = request.app.state.provider_registry

    engine = TradeConstructionEngine(settings, registry)
    try:
        trade = await engine.build_custom(
            ticker=body.ticker.upper(),
            lower_strike=body.lower_strike,
            upper_strike=body.upper_strike,
            short_expiry=body.short_expiry,
            long_expiry=body.long_expiry,
        )
    except ValueError:
        raise_not_found("Trade", body.ticker)
    return _to_response(trade)
