from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.config import EarningsWindowSettings, ScoringSettings
from app.core.enums import RecommendationClass
from app.providers.base import (
    EarningsRecord,
    OptionRecord,
    OptionsChainSnapshot,
    PriceRecord,
    ProviderMeta,
    VolatilitySnapshot,
)
from app.services.liquidity import LiquidityCheckResult
from app.services.scoring import ScoringEngine


@pytest.fixture
def engine():
    return ScoringEngine(ScoringSettings(), EarningsWindowSettings())


@pytest.fixture
def good_earnings():
    return EarningsRecord(
        ticker="AAPL",
        earnings_date=date.today() + timedelta(days=14),
        report_timing="AFTER_CLOSE",
        confidence="CONFIRMED",
        meta=ProviderMeta(source_name="mock", confidence_score=1.0),
    )


@pytest.fixture
def good_price():
    return PriceRecord(
        ticker="AAPL",
        trade_date=date.today(),
        open=190.0,
        high=192.0,
        low=189.0,
        close=191.0,
        volume=5_000_000,
    )


@pytest.fixture
def good_vol():
    return VolatilitySnapshot(
        ticker="AAPL",
        as_of_date=date.today(),
        realized_vol_10d=0.22,
        realized_vol_20d=0.21,
        realized_vol_30d=0.23,
        atr_14d=2.5,
        iv_rank=45.0,
        front_expiry_iv=0.35,
        back_expiry_iv=0.28,
        term_structure_slope=-0.07,
        meta=ProviderMeta(source_name="mock", confidence_score=1.0),
    )


@pytest.fixture
def good_chain():
    spot = 191.0
    front = date.today() + timedelta(days=10)
    back = date.today() + timedelta(days=40)
    options = []
    for exp in [front, back]:
        for offset in [-5, -2.5, 0, 2.5, 5]:
            for otype in ["CALL", "PUT"]:
                options.append(
                    OptionRecord(
                        ticker="AAPL",
                        option_type=otype,
                        strike=spot + offset,
                        expiration=exp,
                        bid=3.0,
                        ask=3.20,
                        volume=800,
                        open_interest=2000,
                        implied_volatility=0.30,
                    )
                )
    return OptionsChainSnapshot(
        ticker="AAPL",
        spot_price=spot,
        snapshot_time=datetime.now(UTC),
        options=options,
        expirations=[front, back],
    )


@pytest.fixture
def good_liquidity():
    return LiquidityCheckResult(passed=True, score=85.0)


def test_score_returns_all_factors(
    engine, good_earnings, good_price, good_vol, good_chain, good_liquidity
):
    result = engine.score("AAPL", good_earnings, good_price, good_vol, good_chain, good_liquidity)
    assert len(result.factors) == 8
    factor_names = {f.name for f in result.factors}
    assert "Liquidity Quality" in factor_names
    assert "Earnings Timing" in factor_names
    assert "Vol Term Structure" in factor_names
    assert "Pre-earnings Containment" in factor_names
    assert "Pricing Efficiency" in factor_names
    assert "Event Cleanliness" in factor_names
    assert "Historical Fit" in factor_names
    assert "IV/HV Gap" in factor_names


def test_score_range(engine, good_earnings, good_price, good_vol, good_chain, good_liquidity):
    result = engine.score("AAPL", good_earnings, good_price, good_vol, good_chain, good_liquidity)
    assert 0 <= result.overall_score <= 100
    for f in result.factors:
        assert 0 <= f.raw_score <= 100
        assert f.weighted_score >= 0


def test_good_candidate_scores_well(
    engine, good_earnings, good_price, good_vol, good_chain, good_liquidity
):
    result = engine.score("AAPL", good_earnings, good_price, good_vol, good_chain, good_liquidity)
    assert result.overall_score >= 60
    assert result.classification in (RecommendationClass.RECOMMEND, RecommendationClass.WATCHLIST)


def test_classification_thresholds(engine, good_earnings, good_price, good_vol, good_chain):
    high_liq = LiquidityCheckResult(passed=True, score=95.0)
    result = engine.score("AAPL", good_earnings, good_price, good_vol, good_chain, high_liq)
    if result.overall_score >= 80:
        assert result.classification == RecommendationClass.RECOMMEND
    elif result.overall_score >= 65:
        assert result.classification == RecommendationClass.WATCHLIST
    else:
        assert result.classification == RecommendationClass.NO_TRADE


def test_risk_warnings_present(
    engine, good_earnings, good_price, good_vol, good_chain, good_liquidity
):
    result = engine.score("AAPL", good_earnings, good_price, good_vol, good_chain, good_liquidity)
    assert len(result.risk_warnings) > 0
    assert any("decision-support" in w.lower() for w in result.risk_warnings)


def test_rationale_not_empty(
    engine, good_earnings, good_price, good_vol, good_chain, good_liquidity
):
    result = engine.score("AAPL", good_earnings, good_price, good_vol, good_chain, good_liquidity)
    assert result.rationale_summary != ""
    assert "AAPL" in result.rationale_summary


def test_unverified_earnings_penalized(engine, good_price, good_vol, good_chain, good_liquidity):
    unverified = EarningsRecord(
        ticker="TEST",
        earnings_date=date.today() + timedelta(days=14),
        confidence="UNVERIFIED",
        meta=ProviderMeta(source_name="mock", confidence_score=0.5),
    )
    confirmed = EarningsRecord(
        ticker="TEST",
        earnings_date=date.today() + timedelta(days=14),
        confidence="CONFIRMED",
        report_timing="AFTER_CLOSE",
        meta=ProviderMeta(source_name="mock", confidence_score=1.0),
    )
    result_unverified = engine.score(
        "TEST", unverified, good_price, good_vol, good_chain, good_liquidity
    )
    result_confirmed = engine.score(
        "TEST", confirmed, good_price, good_vol, good_chain, good_liquidity
    )
    assert result_confirmed.overall_score > result_unverified.overall_score


def test_poor_liquidity_lowers_score(engine, good_earnings, good_price, good_vol, good_chain):
    good_liq = LiquidityCheckResult(passed=True, score=90.0)
    poor_liq = LiquidityCheckResult(passed=False, score=15.0, rejection_reasons=["Low volume"])
    result_good = engine.score("TEST", good_earnings, good_price, good_vol, good_chain, good_liq)
    result_poor = engine.score("TEST", good_earnings, good_price, good_vol, good_chain, poor_liq)
    assert result_good.overall_score > result_poor.overall_score


def test_iv_hv_gap_cheap_iv_scores_high(
    engine, good_earnings, good_price, good_chain, good_liquidity
):
    """When IV is well below HV, the IV/HV Gap factor should score high (options are cheap)."""
    cheap_vol = VolatilitySnapshot(
        ticker="TEST",
        as_of_date=date.today(),
        realized_vol_10d=0.30,
        realized_vol_20d=0.30,
        realized_vol_30d=0.35,
        front_expiry_iv=0.25,  # IV/HV = 0.71 → cheap
        back_expiry_iv=0.22,
        term_structure_slope=-0.05,
        iv_rank=40.0,
        meta=ProviderMeta(source_name="mock", confidence_score=1.0),
    )
    result = engine.score("TEST", good_earnings, good_price, cheap_vol, good_chain, good_liquidity)
    gap_factor = next(f for f in result.factors if f.name == "IV/HV Gap")
    assert gap_factor.raw_score >= 90.0


def test_iv_hv_gap_expensive_iv_scores_low(
    engine, good_earnings, good_price, good_chain, good_liquidity
):
    """When IV far exceeds HV, the IV/HV Gap factor should score low (options expensive)."""
    expensive_vol = VolatilitySnapshot(
        ticker="TEST",
        as_of_date=date.today(),
        realized_vol_10d=0.15,
        realized_vol_20d=0.15,
        realized_vol_30d=0.15,
        front_expiry_iv=0.35,  # IV/HV = 2.33 → very expensive
        back_expiry_iv=0.30,
        term_structure_slope=-0.05,
        iv_rank=80.0,
        meta=ProviderMeta(source_name="mock", confidence_score=1.0),
    )
    result = engine.score(
        "TEST", good_earnings, good_price, expensive_vol, good_chain, good_liquidity
    )
    gap_factor = next(f for f in result.factors if f.name == "IV/HV Gap")
    assert gap_factor.raw_score <= 20.0
    # Should also generate a warning
    assert any("IV/HV ratio" in w for w in result.risk_warnings)
