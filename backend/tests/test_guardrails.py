"""Guardrail tests: mock/live parity, scoring invariants, and trade validation."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.core.config import get_settings
from app.providers.base import (
    EarningsRecord,
    OptionRecord,
    OptionsChainSnapshot,
    PriceRecord,
    ProviderMeta,
    VolatilitySnapshot,
)
from app.providers.mock.volatility import MOCK_VOL_DATA, MockVolatilityProvider
from app.providers.registry import ProviderRegistry
from app.services.strategies.butterfly import ButterflyStrategy
from app.services.strategies.double_calendar import DoubleCalendarStrategy

# ── Mock/Live Parity Guards ──────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", list(MOCK_VOL_DATA.keys()))
async def test_mock_vol_iv_rank_scale(ticker):
    """iv_rank must be on the 0.0–1.0 scale for all mock tickers."""
    provider = MockVolatilityProvider()
    snap = await provider.get_volatility_metrics(ticker)
    assert 0.0 <= snap.iv_rank <= 1.0, (
        f"{ticker}: iv_rank={snap.iv_rank} is not on the 0.0-1.0 scale"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", list(MOCK_VOL_DATA.keys()))
async def test_mock_vol_iv_percentile_scale(ticker):
    """iv_percentile must be on the 0.0–1.0 scale for all mock tickers."""
    provider = MockVolatilityProvider()
    snap = await provider.get_volatility_metrics(ticker)
    assert 0.0 <= snap.iv_percentile <= 1.0, (
        f"{ticker}: iv_percentile={snap.iv_percentile} is not on the 0.0-1.0 scale"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", list(MOCK_VOL_DATA.keys()))
async def test_mock_vol_term_slope_denominator(ticker):
    """term_structure_slope must use back_iv as denominator, matching live provider."""
    provider = MockVolatilityProvider()
    snap = await provider.get_volatility_metrics(ticker)
    if snap.back_expiry_iv and snap.back_expiry_iv > 0:
        expected = (snap.back_expiry_iv - snap.front_expiry_iv) / snap.back_expiry_iv
        assert abs(snap.term_structure_slope - expected) < 0.02, (
            f"{ticker}: slope={snap.term_structure_slope} doesn't match "
            f"(back-front)/back={expected:.4f}"
        )


# ── Scoring Invariants ───────────────────────────────────────────────


def test_scoring_weights_normalize_to_100():
    """Base scoring engine weighted_scores must sum to ≤100 for any raw input."""
    from app.services.scoring import ScoringEngine

    settings = get_settings()
    engine = ScoringEngine(settings.scoring, settings.earnings_window)

    # Simulate all factors at raw_score=100
    total = engine._total_weight
    max_possible = sum(
        100.0 * (w / total)
        for w in [
            settings.scoring.LIQUIDITY_WEIGHT,
            settings.scoring.EARNINGS_TIMING_WEIGHT,
            settings.scoring.VOL_TERM_STRUCTURE_WEIGHT,
            settings.scoring.CONTAINMENT_WEIGHT,
            settings.scoring.PRICING_EFFICIENCY_WEIGHT,
            settings.scoring.EVENT_CLEANLINESS_WEIGHT,
            settings.scoring.HISTORICAL_FIT_WEIGHT,
            settings.scoring.IV_HV_GAP_WEIGHT,
        ]
    )
    assert abs(max_possible - 100.0) < 0.1, (
        f"Base weights normalize to {max_possible:.1f}, expected ~100.0"
    )


def test_double_calendar_score_within_bounds():
    """Double calendar score must be 0-100 even with all bonuses active."""
    settings = get_settings()
    registry = MagicMock(spec=ProviderRegistry)
    dc = DoubleCalendarStrategy(settings, registry)

    meta = ProviderMeta("test")
    earnings = EarningsRecord("TEST", date.today() + timedelta(days=14), "CONFIRMED")
    price = PriceRecord("TEST", date.today(), 100, 100, 100, 100, 1_000_000)
    vol = VolatilitySnapshot(
        ticker="TEST",
        as_of_date=date.today(),
        iv_rank=0.50,
        iv_percentile=0.45,
        front_expiry_iv=0.40,
        back_expiry_iv=0.25,  # strong backwardation → regime filter triggers
        term_structure_slope=-0.20,
        realized_vol_20d=0.25,
        realized_vol_30d=0.22,
        atr_14d=2.0,
        meta=meta,
    )
    chain = OptionsChainSnapshot(
        ticker="TEST",
        spot_price=100.0,
        options=[
            OptionRecord("TEST", "call", 100.0, date.today() + timedelta(days=14),
                         3.0, 3.2, 3.1, 3.1, 100, 500, 0.30, 0.5, 0, 0, 0, 0),
            OptionRecord("TEST", "put", 100.0, date.today() + timedelta(days=14),
                         3.0, 3.2, 3.1, 3.1, 100, 500, 0.30, -0.5, 0, 0, 0, 0),
        ],
        snapshot_time=date.today(),
        meta=meta,
    )
    from app.services.liquidity import LiquidityCheckResult

    liq = LiquidityCheckResult(passed=True, score=90.0, rejection_reasons=[])
    result = dc.calculate_score("TEST", earnings, price, vol, chain, liq)

    assert 0.0 <= result.overall_score <= 100.0, (
        f"DC score {result.overall_score} out of [0, 100] bounds"
    )
    # Verify re-normalization happened: total weight should > 110
    total_w = sum(f.weight for f in result.factors)
    assert total_w > 110, "Expected bonus factors to increase total weight"
    # Verify weighted_scores still sum to ≤100
    total_ws = sum(f.weighted_score for f in result.factors)
    assert total_ws <= 100.1, f"Weighted scores sum {total_ws} exceeds 100"


# ── Trade Structure Validation ───────────────────────────────────────


def test_butterfly_wings_never_collapse():
    """Butterfly must produce distinct wing strikes even at DTE=0."""
    settings = get_settings()
    registry = MagicMock(spec=ProviderRegistry)
    bfly = ButterflyStrategy(settings, registry)

    meta = ProviderMeta("test")
    # DTE = 0 (earnings today)
    earnings = EarningsRecord("TEST", date.today(), "CONFIRMED")
    price = PriceRecord("TEST", date.today(), 100, 100, 100, 100, 1_000_000)
    vol = VolatilitySnapshot(
        ticker="TEST",
        as_of_date=date.today(),
        iv_rank=0.50,
        iv_percentile=0.45,
        front_expiry_iv=0.30,
        back_expiry_iv=0.25,
        term_structure_slope=-0.10,
        realized_vol_20d=0.20,
        atr_14d=2.0,
        meta=meta,
    )
    chain = OptionsChainSnapshot(
        ticker="TEST",
        spot_price=100.0,
        options=[
            OptionRecord("TEST", "put", s, date.today() + timedelta(days=3),
                         1.0, 1.2, 1.1, 1.1, 10, 100, 0.3, -0.3, 0, 0, 0, 0)
            for s in [90.0, 95.0, 100.0, 105.0, 110.0]
        ] + [
            OptionRecord("TEST", "call", s, date.today() + timedelta(days=3),
                         1.0, 1.2, 1.1, 1.1, 10, 100, 0.3, 0.3, 0, 0, 0, 0)
            for s in [90.0, 95.0, 100.0, 105.0, 110.0]
        ],
        snapshot_time=date.today(),
        meta=meta,
    )

    trade = bfly.build_trade_structure(
        "TEST", earnings, price, vol, chain,
        override_short_exp=date.today() + timedelta(days=3),
    )

    assert trade.lower_strike < trade.upper_strike, (
        f"Wings collapsed: lower={trade.lower_strike}, upper={trade.upper_strike}"
    )


# ── Scan Metadata Passthrough ────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_passes_strategy_metadata(client):
    """Scan results must include strategy_type and layer_id for scored tickers."""
    r = await client.post("/api/v1/scan/run", json={"tickers": ["AAPL"]})
    assert r.status_code == 200
    data = r.json()
    for result in data["results"]:
        if result["classification"] in ("RECOMMEND", "WATCHLIST"):
            assert result["strategy_type"] is not None, (
                f"{result['ticker']}: strategy_type missing from API response"
            )
            assert result["layer_id"] is not None, (
                f"{result['ticker']}: layer_id missing from API response"
            )
            assert result["account_id"] is not None, (
                f"{result['ticker']}: account_id missing from API response"
            )
