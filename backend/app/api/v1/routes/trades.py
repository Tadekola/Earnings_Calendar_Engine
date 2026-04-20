from __future__ import annotations

import time

from fastapi import APIRouter, Query, Request

from app.core.errors import raise_bad_request, raise_not_found
from app.schemas.trade import (
    RecommendedTradeResponse,
    TradeBuildRequest,
    TradeLegResponse,
    TradeRepriceRequest,
)
from app.services.trade_builder import ConstructedTrade, TradeConstructionEngine

router = APIRouter(prefix="/trades", tags=["trades"])

# Short-lived in-process cache for the recommended-trade build.
# Building a trade fetches the full Tradier options chain (~15-20 expiration
# calls, 10-20s wall time). Users often click between WATCHLIST/RECOMMEND
# tickers rapidly; caching for 60s makes the second click feel instant
# without sacrificing price freshness (legs are requoted on explicit refresh
# via the `refresh=true` query param).
_TRADE_CACHE_TTL_SECONDS = 60
_trade_cache: dict[tuple[str, str | None], tuple[float, RecommendedTradeResponse]] = {}


def _to_response(trade: ConstructedTrade) -> RecommendedTradeResponse:
    legs = [
        TradeLegResponse(
            leg_number=leg.leg_number,
            option_type=leg.option_type,
            side=leg.side,
            strike=leg.strike,
            expiration=leg.expiration,
            quantity=leg.quantity,
            bid=leg.bid,
            ask=leg.ask,
            mid=leg.mid,
            implied_volatility=leg.option.implied_volatility if leg.option else None,
            delta=leg.option.delta if leg.option else None,
            theta=leg.option.theta if leg.option else None,
            vega=leg.option.vega if leg.option else None,
            open_interest=leg.option.open_interest if leg.option else None,
            volume=leg.option.volume if leg.option else None,
            spread_to_mid=leg.spread_to_mid,
        )
        for leg in trade.legs
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
        strategy_type=trade.strategy_type,
        legs=legs,
    )


@router.get("/{ticker}/recommended", response_model=RecommendedTradeResponse)
async def get_recommended_trade(
    request: Request,
    ticker: str,
    strategy: str | None = None,
    refresh: bool = Query(False, description="Bypass the 60s cache and rebuild"),
) -> RecommendedTradeResponse:
    ticker = ticker.upper()
    cache_key = (ticker, strategy.upper() if strategy else None)

    if not refresh:
        hit = _trade_cache.get(cache_key)
        if hit is not None and (time.monotonic() - hit[0]) < _TRADE_CACHE_TTL_SECONDS:
            return hit[1]

    settings = request.app.state.settings
    registry = request.app.state.provider_registry

    engine = TradeConstructionEngine(settings, registry)
    if strategy:
        from app.services.base_strategy import StrategyFactory

        strategies = StrategyFactory(settings, registry).get_active_strategies()
        selected_strat = next(
            (s for s in strategies if s.strategy_type.upper() == strategy.upper()), None
        )
        if selected_strat:
            engine = TradeConstructionEngine(settings, registry, selected_strat)

    try:
        trade = await engine.build_recommended(ticker)
    except ValueError:
        raise_not_found("Trade", ticker)

    response = _to_response(trade)
    _trade_cache[cache_key] = (time.monotonic(), response)
    return response


@router.post("/build", response_model=RecommendedTradeResponse)
async def build_trade(request: Request, body: TradeBuildRequest) -> RecommendedTradeResponse:
    settings = request.app.state.settings
    registry = request.app.state.provider_registry

    engine = TradeConstructionEngine(settings, registry)
    if body.strategy_type:
        from app.services.base_strategy import StrategyFactory

        strategies = StrategyFactory(settings, registry).get_active_strategies()
        selected_strat = next(
            (s for s in strategies if s.strategy_type.upper() == body.strategy_type.upper()), None
        )
        if selected_strat:
            engine = TradeConstructionEngine(settings, registry, selected_strat)

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
async def reprice_trade(request: Request, req: TradeRepriceRequest) -> RecommendedTradeResponse:
    settings = request.app.state.settings
    registry = request.app.state.provider_registry

    try:
        from app.services.base_strategy import StrategyFactory

        strategy_factory = StrategyFactory(settings, registry)
        strat_id = req.strategy_type or "DOUBLE_CALENDAR"
        strategy = strategy_factory.get_strategy(strat_id)

        # We need the underlying data to rebuild
        earnings = await registry.earnings.get_earnings_date(req.ticker)
        price = await registry.price.get_current_price(req.ticker)
        vol = await registry.volatility.get_volatility_metrics(req.ticker)
        chain = await registry.options.get_options_chain(req.ticker)

        if not price or not vol or not chain:
            raise_bad_request("Missing data to reprice trade")

        short_exp = req.short_expiry
        long_exp = req.long_expiry

        trade = strategy.build_trade_structure(
            ticker=req.ticker,
            earnings=earnings,
            price=price,
            vol=vol,
            chain=chain,
            override_lower=req.lower_strike,
            override_upper=req.upper_strike,
            override_short_exp=short_exp,
            override_long_exp=long_exp,
        )
    except ValueError:
        raise_not_found("Trade", req.ticker)
    return _to_response(trade)
