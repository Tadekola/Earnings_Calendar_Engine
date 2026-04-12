from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.enums import LegSide, OptionType, RecommendationClass
from app.providers.registry import ProviderRegistry
from app.services.trade_builder import TradeConstructionEngine


@pytest.fixture
def engine():
    settings = get_settings()
    settings.data.ALLOW_SIMULATION = True
    registry = ProviderRegistry(settings)
    registry.initialize()
    return TradeConstructionEngine(settings, registry)


@pytest.mark.asyncio
async def test_build_recommended_aapl(engine):
    trade = await engine.build_recommended("AAPL")
    assert trade.ticker == "AAPL"
    assert trade.spot_price > 0
    assert len(trade.legs) == 4
    assert trade.lower_strike < trade.upper_strike
    assert trade.short_expiry < trade.long_expiry
    assert trade.total_debit_mid != 0
    assert trade.risk_disclaimer != ""


@pytest.mark.asyncio
async def test_legs_structure(engine):
    trade = await engine.build_recommended("MSFT")
    assert len(trade.legs) == 4

    leg_types = [(leg.option_type, leg.side) for leg in trade.legs]
    assert (OptionType.PUT, LegSide.SELL) in leg_types
    assert (OptionType.PUT, LegSide.BUY) in leg_types
    assert (OptionType.CALL, LegSide.SELL) in leg_types
    assert (OptionType.CALL, LegSide.BUY) in leg_types

    for leg in trade.legs:
        assert leg.leg_number in (1, 2, 3, 4)
        assert leg.strike > 0
        assert getattr(leg, "bid", 0) >= 0
        assert getattr(leg, "ask", 0) >= 0


@pytest.mark.asyncio
async def test_sell_legs_short_buy_legs_long(engine):
    trade = await engine.build_recommended("NVDA")
    for leg in trade.legs:
        if leg.side == LegSide.SELL:
            assert leg.expiration == trade.short_expiry
        else:
            assert leg.expiration == trade.long_expiry


@pytest.mark.asyncio
async def test_no_earnings_raises(engine):
    with pytest.raises(ValueError, match="No earnings date"):
        await engine.build_recommended("SPY")


@pytest.mark.asyncio
async def test_build_custom_overrides(engine):
    trade = await engine.build_custom(
        "AAPL",
        lower_strike=180.0,
        upper_strike=200.0,
    )
    assert trade.lower_strike == 180.0
    assert trade.upper_strike == 200.0


@pytest.mark.asyncio
async def test_scoring_integrated(engine):
    trade = await engine.build_recommended("GOOGL")
    assert trade.overall_score > 0
    assert trade.classification in (
        RecommendationClass.RECOMMEND,
        RecommendationClass.WATCHLIST,
        RecommendationClass.NO_TRADE,
    )


@pytest.mark.asyncio
async def test_key_risks_present(engine):
    trade = await engine.build_recommended("TSLA")
    assert len(trade.key_risks) >= 3
    assert any("earnings" in r.lower() for r in trade.key_risks)


@pytest.mark.asyncio
async def test_profit_zone(engine):
    trade = await engine.build_recommended("AMD")
    assert trade.profit_zone_low < trade.lower_strike
    assert trade.profit_zone_high > trade.upper_strike


@pytest.mark.asyncio
async def test_pessimistic_debit(engine):
    trade = await engine.build_recommended("META")
    # Pessimistic should be >= mid debit (buying at ask, selling at bid)
    assert abs(trade.total_debit_pessimistic) >= abs(trade.total_debit_mid) - 0.01
