from datetime import date
from unittest.mock import MagicMock

import pytest

from app.core.config import get_settings
from app.core.enums import LegSide, OptionType
from app.providers.base import (
    EarningsRecord,
    OptionRecord,
    OptionsChainSnapshot,
    PriceRecord,
    VolatilitySnapshot,
)
from app.providers.registry import ProviderRegistry
from app.services.base_strategy import StrategyFactory
from app.services.strategies.butterfly import ButterflyStrategy
from app.services.strategies.double_calendar import DoubleCalendarStrategy


@pytest.fixture
def live_settings():
    return get_settings()


@pytest.fixture
def mock_registry():
    registry = MagicMock(spec=ProviderRegistry)
    return registry


@pytest.fixture
def mock_chain():
    from app.providers.base import ProviderMeta

    meta = ProviderMeta("unknown")
    # ticker, option_type, strike, expiration, bid, ask, mid, last,
    # volume, open_interest, implied_volatility, delta, gamma, theta,
    # vega, rho
    return OptionsChainSnapshot(
        ticker="TEST",
        spot_price=100.0,
        options=[
            OptionRecord(
                "TEST",
                "put",
                90.0,
                date(2026, 4, 24),
                1.0,
                1.2,
                1.1,
                1.1,
                10,
                100,
                0.3,
                -0.1,
                0,
                0,
                0,
                0,
            ),
            OptionRecord(
                "TEST",
                "put",
                100.0,
                date(2026, 4, 24),
                3.0,
                3.2,
                3.1,
                3.1,
                10,
                100,
                0.3,
                -0.5,
                0,
                0,
                0,
                0,
            ),
            OptionRecord(
                "TEST",
                "call",
                100.0,
                date(2026, 4, 24),
                3.0,
                3.2,
                3.1,
                3.1,
                10,
                100,
                0.3,
                0.5,
                0,
                0,
                0,
                0,
            ),
            OptionRecord(
                "TEST",
                "call",
                110.0,
                date(2026, 4, 24),
                1.0,
                1.2,
                1.1,
                1.1,
                10,
                100,
                0.3,
                0.1,
                0,
                0,
                0,
                0,
            ),
        ],
        snapshot_time=date.today(),
        meta=meta,
    )


@pytest.fixture
def mock_vol():
    from app.providers.base import ProviderMeta

    meta = ProviderMeta("unknown")
    return VolatilitySnapshot(
        ticker="TEST",
        as_of_date=date.today(),
        iv_rank=0.9,
        iv_percentile=90.0,
        front_expiry_iv=0.30,
        back_expiry_iv=0.25,
        term_structure_slope=-0.15,
        realized_vol_20d=0.20,
        atr_14d=2.0,
        meta=meta,
    )


def test_strategy_factory(live_settings, mock_registry):
    factory = StrategyFactory(live_settings, mock_registry)
    strategies = factory.get_active_strategies()
    assert len(strategies) == 2
    assert isinstance(strategies[0], DoubleCalendarStrategy)
    assert isinstance(strategies[1], ButterflyStrategy)
    assert strategies[0].strategy_type == "DOUBLE_CALENDAR"
    assert strategies[1].strategy_type == "IRON_BUTTERFLY_ATM"


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
    ivp_factor = next(f for f in score.factors if f.name == "Implied Volatility Percentile")
    assert ivp_factor.raw_score == 100.0


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

    # Check structure: Long Put 90, Short Put 100, Short Call 100, Long Call 110
    leg1 = next(leg for leg in trade.legs if leg.leg_number == 1)
    assert leg1.side == LegSide.BUY and leg1.option_type == OptionType.PUT and leg1.strike == 90.0
    assert leg1.debit == 1.1  # Mid price

    leg2 = next(leg for leg in trade.legs if leg.leg_number == 2)
    assert leg2.side == LegSide.SELL and leg2.option_type == OptionType.PUT and leg2.strike == 100.0
    assert leg2.debit == -3.1

    leg3 = next(leg for leg in trade.legs if leg.leg_number == 3)
    assert (
        leg3.side == LegSide.SELL and leg3.option_type == OptionType.CALL and leg3.strike == 100.0
    )
    assert leg3.debit == -3.1

    leg4 = next(leg for leg in trade.legs if leg.leg_number == 4)
    assert leg4.side == LegSide.BUY and leg4.option_type == OptionType.CALL and leg4.strike == 110.0
    assert leg4.debit == 1.1

    # Total debit logic
    # Total debit = 1.1 - 3.1 - 3.1 + 1.1 = -4.0 (Credit)
    assert trade.total_debit_mid == -4.0
    assert trade.estimated_max_loss == 6.0  # Spread width 10.0 - 4.0 credit
    assert trade.profit_zone_low == 96.0  # 100 - 4.0 credit
    assert trade.profit_zone_high == 104.0  # 100 + 4.0 credit


# --------------------------------------------------------------------------
# Assignment-risk warnings: must appear on equity butterflies, absent on XSP
# --------------------------------------------------------------------------


def _xsp_chain(mock_chain):
    """Clone mock_chain with ticker rewritten to XSP."""
    new_options = []
    for o in mock_chain.options:
        new_options.append(
            OptionRecord(
                "XSP",
                o.option_type,
                o.strike,
                o.expiration,
                o.bid,
                o.ask,
                o.mid,
                o.last,
                o.volume,
                o.open_interest,
                o.implied_volatility,
                o.delta,
                o.gamma,
                o.theta,
                o.vega,
                o.rho,
            )
        )
    return OptionsChainSnapshot(
        ticker="XSP",
        spot_price=mock_chain.spot_price,
        options=new_options,
        snapshot_time=mock_chain.snapshot_time,
        meta=mock_chain.meta,
    )


def test_butterfly_equity_has_assignment_warning(
    live_settings, mock_registry, mock_chain, mock_vol
):
    bfly = ButterflyStrategy(live_settings, mock_registry)
    price = PriceRecord("TEST", date.today(), 100.0, 100.0, 100.0, 100.0, 1000)
    earnings = EarningsRecord("TEST", date(2026, 4, 20), "CONFIRMED")
    liq = bfly.validate_liquidity(price, mock_chain, date(2026, 4, 24), date(2026, 4, 24))

    score = bfly.calculate_score("TEST", earnings, price, mock_vol, mock_chain, liq)
    warnings_text = " ".join(score.risk_warnings)
    assert "Early assignment risk" in warnings_text
    assert "Ex-dividend" in warnings_text

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
    risks_text = " ".join(trade.key_risks)
    assert "Early assignment risk" in risks_text
    assert "Ex-dividend not checked" in risks_text


def test_butterfly_xsp_has_no_assignment_warning(
    live_settings, mock_registry, mock_chain, mock_vol
):
    bfly = ButterflyStrategy(live_settings, mock_registry)
    price = PriceRecord("XSP", date.today(), 100.0, 100.0, 100.0, 100.0, 1000)
    earnings = EarningsRecord("XSP", date(2026, 4, 20), "CONFIRMED")
    xsp_chain = _xsp_chain(mock_chain)
    liq = bfly.validate_liquidity(price, xsp_chain, date(2026, 4, 24), date(2026, 4, 24))

    score = bfly.calculate_score("XSP", earnings, price, mock_vol, xsp_chain, liq)
    warnings_text = " ".join(score.risk_warnings)
    assert "Early assignment risk" not in warnings_text
    assert "Ex-dividend" not in warnings_text

    trade = bfly.build_trade_structure(
        ticker="XSP",
        earnings=earnings,
        price=price,
        vol=mock_vol,
        chain=xsp_chain,
        override_lower=90.0,
        override_upper=110.0,
        override_short_exp=date(2026, 4, 24),
    )
    risks_text = " ".join(trade.key_risks)
    assert "Early assignment risk" not in risks_text
    assert "Ex-dividend not checked" not in risks_text


def test_double_calendar_equity_has_assignment_warning(
    live_settings, mock_registry, mock_chain, mock_vol
):
    dc = DoubleCalendarStrategy(live_settings, mock_registry)
    price = PriceRecord("TEST", date.today(), 100.0, 100.0, 100.0, 100.0, 1000)
    earnings = EarningsRecord("TEST", date(2026, 4, 28), "CONFIRMED")

    # Need a chain with both short and long expirations
    from app.providers.base import ProviderMeta

    long_exp = date(2026, 5, 15)
    long_legs = []
    for o in mock_chain.options:
        long_legs.append(
            OptionRecord(
                "TEST",
                o.option_type,
                o.strike,
                long_exp,
                o.bid + 0.5,
                o.ask + 0.5,
                o.mid + 0.5,
                o.last,
                o.volume,
                o.open_interest,
                o.implied_volatility,
                o.delta,
                o.gamma,
                o.theta,
                o.vega,
                o.rho,
            )
        )
    chain = OptionsChainSnapshot(
        ticker="TEST",
        spot_price=100.0,
        options=list(mock_chain.options) + long_legs,
        snapshot_time=date.today(),
        meta=ProviderMeta("unknown"),
    )

    trade = dc.build_trade_structure(
        ticker="TEST",
        earnings=earnings,
        price=price,
        vol=mock_vol,
        chain=chain,
        override_lower=90.0,
        override_upper=110.0,
        override_short_exp=date(2026, 4, 24),
        override_long_exp=long_exp,
    )
    risks_text = " ".join(trade.key_risks)
    assert "American-style equity options" in risks_text
    assert "Ex-dividend not checked" in risks_text
