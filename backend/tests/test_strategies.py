from datetime import date
from unittest.mock import MagicMock

import pytest
from app.core.config import Settings
from app.core.enums import LegSide, OptionType, RecommendationClass
from app.providers.base import (
    EarningsRecord,
    OptionsChainSnapshot,
    OptionRecord,
    PriceRecord,
    ProviderMeta,
    VolatilitySnapshot,
)
from app.providers.registry import ProviderRegistry
from app.services.base_strategy import StrategyFactory
from app.services.strategies.butterfly import ButterflyStrategy
from app.services.strategies.double_calendar import DoubleCalendarStrategy


from app.core.config import get_settings

@pytest.fixture
def live_settings():
    return get_settings()

@pytest.fixture
def mock_registry():
    registry = MagicMock(spec=ProviderRegistry)
    return registry


@pytest.fixture
def mock_chain():
    return OptionsChainSnapshot(
        ticker="TEST",
        spot_price=100.0,
        snapshot_time=date.today(),
        expirations=[date(2026, 4, 24), date(2026, 5, 8)],
        options=[
            OptionRecord("TEST", "put", 90.0, date(2026, 4, 24), bid=1.0, ask=1.2, mid=1.1),
            OptionRecord("TEST", "put", 100.0, date(2026, 4, 24), bid=3.0, ask=3.2, mid=3.1),
            OptionRecord("TEST", "call", 100.0, date(2026, 4, 24), bid=3.0, ask=3.2, mid=3.1),
            OptionRecord("TEST", "call", 110.0, date(2026, 4, 24), bid=1.0, ask=1.2, mid=1.1),
            
            # Additional options for Double Calendar back month
            OptionRecord("TEST", "put", 90.0, date(2026, 5, 8), bid=2.0, ask=2.2, mid=2.1),
            OptionRecord("TEST", "put", 100.0, date(2026, 5, 8), bid=4.0, ask=4.2, mid=4.1),
            OptionRecord("TEST", "call", 100.0, date(2026, 5, 8), bid=4.0, ask=4.2, mid=4.1),
            OptionRecord("TEST", "call", 110.0, date(2026, 5, 8), bid=2.0, ask=2.2, mid=2.1),
        ],
    )


@pytest.fixture
def mock_vol():
    return VolatilitySnapshot(
        ticker="TEST",
        as_of_date=date.today(),
        iv_percentile=0.90,  # High IVP to trigger Butterfly bonus
        front_expiry_iv=0.40,
        back_expiry_iv=0.30, # Backwardation to trigger Calendar bonus
        atr_14d=2.0,
    )


def test_strategy_factory(live_settings, mock_registry):
    factory = StrategyFactory(live_settings, mock_registry)
    strategies = factory.get_active_strategies()
    assert len(strategies) == 2
    assert isinstance(strategies[0], DoubleCalendarStrategy)
    assert isinstance(strategies[1], ButterflyStrategy)
    assert strategies[0].strategy_type == "DOUBLE_CALENDAR"
    assert strategies[1].strategy_type == "BUTTERFLY"


def test_butterfly_scoring_iv_percentile(live_settings, mock_registry, mock_chain, mock_vol):
    bfly = ButterflyStrategy(live_settings, mock_registry)
    price = PriceRecord("TEST", date.today(), 100.0, 100.0, 100.0, 100.0, 1000)
    earnings = EarningsRecord("TEST", date(2026, 4, 20), "CONFIRMED")
    
    # Run calculate_score
    liq = bfly.validate_liquidity(price, mock_chain, date(2026, 4, 24), date(2026, 4, 24))
    score = bfly.calculate_score("TEST", earnings, price, mock_vol, mock_chain, liq)
    
    assert score.ticker == "TEST"
    assert len(score.factors) >= 2
    # IV Percentile is > 0.8, should be maxed out to 100 raw score
    ivp_factor = next(f for f in score.factors if f.name == "IV Percentile")
    assert ivp_factor.raw_score == 100.0
    assert ivp_factor.weighted_score == 35.0


def test_butterfly_build_trade_structure(live_settings, mock_registry, mock_chain, mock_vol):
    bfly = ButterflyStrategy(live_settings, mock_registry)
    price = PriceRecord("TEST", date.today(), 100.0, 100.0, 100.0, 100.0, 1000)
    earnings = EarningsRecord("TEST", date(2026, 4, 20), "CONFIRMED")
    
    trade = bfly.build_trade_structure(
        ticker="TEST",
        earnings=earnings,
        price=price,
        vol=mock_vol,
        chain=mock_chain,
        override_lower=90.0,
        override_upper=110.0,
        override_short_exp=date(2026, 4, 24),
    )
    
    assert trade.ticker == "TEST"
    assert trade.strategy_type == "BUTTERFLY"
    assert len(trade.legs) == 4
    
    # All legs should have same expiration
    assert all(leg.expiration == date(2026, 4, 24) for leg in trade.legs)
    assert trade.short_expiry == date(2026, 4, 24)
    assert trade.long_expiry == date(2026, 4, 24)
    
    # Check structure: Long Put 90, Short Put 100, Short Call 100, Long Call 110
    leg1 = next(l for l in trade.legs if l.leg_number == 1)
    assert leg1.side == LegSide.BUY and leg1.option_type == OptionType.PUT and leg1.strike == 90.0
    assert leg1.debit == 1.1  # Mid price
    
    leg2 = next(l for l in trade.legs if l.leg_number == 2)
    assert leg2.side == LegSide.SELL and leg2.option_type == OptionType.PUT and leg2.strike == 100.0
    assert leg2.debit == -3.1
    
    leg3 = next(l for l in trade.legs if l.leg_number == 3)
    assert leg3.side == LegSide.SELL and leg3.option_type == OptionType.CALL and leg3.strike == 100.0
    assert leg3.debit == -3.1
    
    leg4 = next(l for l in trade.legs if l.leg_number == 4)
    assert leg4.side == LegSide.BUY and leg4.option_type == OptionType.CALL and leg4.strike == 110.0
    assert leg4.debit == 1.1

    # Total debit logic
    # Total debit = 1.1 - 3.1 - 3.1 + 1.1 = -4.0 (Credit)
    assert trade.total_debit_mid == -4.0
    assert trade.estimated_max_loss == 6.0  # Spread width 10.0 - 4.0 credit
    assert trade.profit_zone_low == 96.0  # 100 - 4.0 credit
    assert trade.profit_zone_high == 104.0 # 100 + 4.0 credit
