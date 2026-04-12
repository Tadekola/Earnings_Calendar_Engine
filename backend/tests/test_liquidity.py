from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.config import LiquiditySettings
from app.providers.base import OptionRecord, OptionsChainSnapshot, PriceRecord
from app.services.liquidity import LiquidityEngine


@pytest.fixture
def engine():
    return LiquidityEngine(LiquiditySettings())


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
def low_volume_price():
    return PriceRecord(
        ticker="ILLQ",
        trade_date=date.today(),
        open=10.0,
        high=10.5,
        low=9.5,
        close=10.0,
        volume=50_000,
    )


def _make_chain(
    spot: float, front_exp: date, back_exp: date, good_liquidity: bool = True
) -> OptionsChainSnapshot:
    options = []
    for exp in [front_exp, back_exp]:
        for strike_offset in [-5, -2.5, 0, 2.5, 5]:
            strike = spot + strike_offset
            vol = 500 if good_liquidity else 10
            oi = 1000 if good_liquidity else 5
            bid = 3.00 if good_liquidity else 0.10
            ask = 3.10 if good_liquidity else 0.80
            for otype in ["CALL", "PUT"]:
                options.append(
                    OptionRecord(
                        ticker="TEST",
                        option_type=otype,
                        strike=strike,
                        expiration=exp,
                        bid=bid,
                        ask=ask,
                        volume=vol,
                        open_interest=oi,
                        implied_volatility=0.30,
                    )
                )
    return OptionsChainSnapshot(
        ticker="TEST",
        spot_price=spot,
        snapshot_time=datetime.now(UTC),
        options=options,
        expirations=[front_exp, back_exp],
    )


def test_stock_liquidity_passes(engine, good_price):
    result = engine.evaluate_stock_liquidity(good_price)
    assert result.passed is True
    assert result.score > 50


def test_stock_liquidity_fails(engine, low_volume_price):
    result = engine.evaluate_stock_liquidity(low_volume_price)
    assert result.passed is False
    assert len(result.rejection_reasons) > 0


def test_options_liquidity_good(engine):
    front = date.today() + timedelta(days=10)
    back = date.today() + timedelta(days=40)
    chain = _make_chain(190.0, front, back, good_liquidity=True)
    result = engine.evaluate_options_liquidity(chain, front, back)
    assert result.passed is True
    assert result.score > 50


def test_options_liquidity_poor(engine):
    front = date.today() + timedelta(days=10)
    back = date.today() + timedelta(days=40)
    chain = _make_chain(190.0, front, back, good_liquidity=False)
    result = engine.evaluate_options_liquidity(chain, front, back)
    assert result.passed is False
    assert len(result.rejection_reasons) > 0


def test_options_liquidity_no_expirations(engine):
    chain = OptionsChainSnapshot(
        ticker="EMPTY",
        spot_price=100.0,
        snapshot_time=datetime.now(UTC),
        options=[],
        expirations=[],
    )
    front = date.today() + timedelta(days=10)
    back = date.today() + timedelta(days=40)
    result = engine.evaluate_options_liquidity(chain, front, back)
    assert result.passed is False


def test_full_evaluation(engine, good_price):
    front = date.today() + timedelta(days=10)
    back = date.today() + timedelta(days=40)
    chain = _make_chain(191.0, front, back, good_liquidity=True)
    result = engine.evaluate_full(good_price, chain, front, back)
    assert result.score > 0
    assert "avg_stock_volume" in result.details
