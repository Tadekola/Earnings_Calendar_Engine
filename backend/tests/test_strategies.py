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
    from app.services.strategies.xsp_butterfly import XSPButterflyStrategy

    factory = StrategyFactory(live_settings, mock_registry)
    strategies = factory.get_active_strategies()
    assert len(strategies) == 3
    assert isinstance(strategies[0], DoubleCalendarStrategy)
    assert isinstance(strategies[1], ButterflyStrategy)
    assert isinstance(strategies[2], XSPButterflyStrategy)
    assert strategies[0].strategy_type == "DOUBLE_CALENDAR"
    assert strategies[1].strategy_type == "IRON_BUTTERFLY_ATM"
    assert strategies[2].strategy_type == "XSP_IRON_BUTTERFLY"


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


# --------------------------------------------------------------------------
# XSP butterfly scorer — regime-aware scoring for index butterflies
# --------------------------------------------------------------------------


def _xsp_chain_with_expiry(days_out: int, spot: float = 500.0) -> OptionsChainSnapshot:
    """Build an XSP options chain with a single expiry N days out."""
    from datetime import timedelta

    from app.providers.base import ProviderMeta

    exp = date.today() + timedelta(days=days_out)
    opts = []
    for strike, bid, ask, delta in [
        (spot - 10, 1.0, 1.2, -0.20),
        (spot, 3.0, 3.2, -0.50),
    ]:
        opts.append(
            OptionRecord(
                "XSP", "put", strike, exp,
                bid, ask, (bid + ask) / 2, (bid + ask) / 2,
                50, 500, 0.15, delta, 0, 0, 0, 0,
            )
        )
    for strike, bid, ask, delta in [
        (spot, 3.0, 3.2, 0.50),
        (spot + 10, 1.0, 1.2, 0.20),
    ]:
        opts.append(
            OptionRecord(
                "XSP", "call", strike, exp,
                bid, ask, (bid + ask) / 2, (bid + ask) / 2,
                50, 500, 0.15, delta, 0, 0, 0, 0,
            )
        )
    return OptionsChainSnapshot(
        ticker="XSP",
        spot_price=spot,
        options=opts,
        expirations=[exp],
        snapshot_time=date.today(),
        meta=ProviderMeta("unknown"),
    )


def _vol_snapshot(
    iv_rank: float = 0.45,  # 45% — sweet spot
    realized: float = 0.10,  # 10% — very quiet
    slope: float = 0.05,  # mild contango
    atr: float = 4.0,  # 0.8% of spot=500
    front_iv: float = 0.15,
) -> VolatilitySnapshot:
    from app.providers.base import ProviderMeta

    return VolatilitySnapshot(
        ticker="XSP",
        as_of_date=date.today(),
        iv_rank=iv_rank,
        iv_percentile=iv_rank * 100,
        front_expiry_iv=front_iv,
        back_expiry_iv=front_iv - (slope * front_iv),
        term_structure_slope=slope,
        realized_vol_20d=realized,
        atr_14d=atr,
        meta=ProviderMeta("unknown"),
    )


def test_xsp_butterfly_ideal_regime_scores_recommend(live_settings, mock_registry):
    from app.services.strategies.xsp_butterfly import XSPButterflyStrategy

    xsp = XSPButterflyStrategy(live_settings, mock_registry)
    chain = _xsp_chain_with_expiry(10)  # 10 DTE — sweet spot
    vol = _vol_snapshot(iv_rank=0.45, realized=0.10, slope=0.05, atr=4.0)  # ideal
    price = PriceRecord("XSP", date.today(), 500.0, 500.0, 500.0, 500.0, 1000)
    liq = type("L", (), {"score": 85.0})()

    result = xsp.calculate_score("XSP", None, price, vol, chain, liq)

    assert result.classification.value == "RECOMMEND", (
        f"Expected RECOMMEND, got {result.classification} with score {result.overall_score}"
    )
    assert result.overall_score >= 80.0
    # XSP must have no assignment warnings
    assert result.risk_warnings == []


def test_xsp_butterfly_crisis_regime_hard_rejected(live_settings, mock_registry):
    from app.services.strategies.xsp_butterfly import XSPButterflyStrategy

    xsp = XSPButterflyStrategy(live_settings, mock_registry)
    chain = _xsp_chain_with_expiry(10)
    vol = _vol_snapshot(realized=0.40)  # 40% RV = crisis
    price = PriceRecord("XSP", date.today(), 500.0, 500.0, 500.0, 500.0, 1000)
    liq = type("L", (), {"score": 85.0})()

    result = xsp.calculate_score("XSP", None, price, vol, chain, liq)

    assert result.classification.value == "NO_TRADE"
    assert result.overall_score == 0.0
    assert any("crisis regime" in w.lower() for w in result.risk_warnings)


def test_xsp_butterfly_severe_backwardation_hard_rejected(live_settings, mock_registry):
    from app.services.strategies.xsp_butterfly import XSPButterflyStrategy

    xsp = XSPButterflyStrategy(live_settings, mock_registry)
    chain = _xsp_chain_with_expiry(10)
    vol = _vol_snapshot(slope=-0.30)  # severe backwardation
    price = PriceRecord("XSP", date.today(), 500.0, 500.0, 500.0, 500.0, 1000)
    liq = type("L", (), {"score": 85.0})()

    result = xsp.calculate_score("XSP", None, price, vol, chain, liq)

    assert result.classification.value == "NO_TRADE"
    assert any("backwardation" in w.lower() for w in result.risk_warnings)


def test_xsp_butterfly_complacent_low_iv_scores_low(live_settings, mock_registry):
    from app.services.strategies.xsp_butterfly import XSPButterflyStrategy

    xsp = XSPButterflyStrategy(live_settings, mock_registry)
    chain = _xsp_chain_with_expiry(10)
    vol = _vol_snapshot(iv_rank=0.05, realized=0.08, slope=0.03)  # IVR 5%, very low
    price = PriceRecord("XSP", date.today(), 500.0, 500.0, 500.0, 500.0, 1000)
    liq = type("L", (), {"score": 85.0})()

    result = xsp.calculate_score("XSP", None, price, vol, chain, liq)

    # With IV Rank 5%, the IV factor scores 10 -> weighted 2.0
    # Overall should not reach RECOMMEND
    assert result.overall_score < 80.0
    assert result.classification.value != "RECOMMEND"


def test_xsp_butterfly_no_expiry_in_window_rejected(live_settings, mock_registry):
    from app.services.strategies.xsp_butterfly import XSPButterflyStrategy

    xsp = XSPButterflyStrategy(live_settings, mock_registry)
    # Only 1 DTE — outside 3-30 window
    chain = _xsp_chain_with_expiry(1)
    vol = _vol_snapshot()
    price = PriceRecord("XSP", date.today(), 500.0, 500.0, 500.0, 500.0, 1000)
    liq = type("L", (), {"score": 85.0})()

    result = xsp.calculate_score("XSP", None, price, vol, chain, liq)

    assert result.classification.value == "NO_TRADE"
    assert any("3-30 DTE" in w for w in result.risk_warnings)


def test_xsp_strategy_factory_lookup(live_settings, mock_registry):
    from app.services.strategies.xsp_butterfly import XSPButterflyStrategy

    factory = StrategyFactory(live_settings, mock_registry)
    strat = factory.get_strategy("XSP_IRON_BUTTERFLY")
    assert isinstance(strat, XSPButterflyStrategy)
    assert strat.strategy_type == "XSP_IRON_BUTTERFLY"


def test_xsp_butterfly_prefers_7_to_14_dte_expiry(live_settings, mock_registry):
    """_select_short_expiry should prefer a 7-14 DTE expiry when available."""
    from datetime import timedelta

    from app.services.strategies.xsp_butterfly import XSPButterflyStrategy

    xsp = XSPButterflyStrategy(live_settings, mock_registry)
    today = date.today()
    expirations = [
        today + timedelta(days=1),   # too short
        today + timedelta(days=10),  # sweet spot
        today + timedelta(days=30),  # acceptable but not preferred
    ]
    # earnings_date is irrelevant for XSP override
    chosen = xsp._select_short_expiry(expirations, today)
    assert (chosen - today).days == 10


def test_equity_butterfly_cap_config_flag_exists(live_settings):
    assert hasattr(live_settings.scoring, "CAP_EQUITY_BUTTERFLIES")
    assert live_settings.scoring.CAP_EQUITY_BUTTERFLIES is True
