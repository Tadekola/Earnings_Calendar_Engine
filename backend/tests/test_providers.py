from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.providers.mock.earnings import MockEarningsProvider
from app.providers.mock.market_data import MockPriceProvider
from app.providers.mock.options import MockOptionsProvider
from app.providers.mock.volatility import MockVolatilityProvider


@pytest.mark.asyncio
async def test_mock_earnings_upcoming():
    provider = MockEarningsProvider()
    tickers = ["AAPL", "MSFT", "NVDA", "SPY"]
    results = await provider.get_upcoming_earnings(tickers, days_ahead=30)
    assert len(results) > 0
    for r in results:
        assert r.ticker in tickers
        assert r.earnings_date > date.today()
        assert r.meta.source_name == "mock_earnings"
        assert r.meta.confidence_score > 0


@pytest.mark.asyncio
async def test_mock_earnings_no_earnings_etf():
    provider = MockEarningsProvider()
    result = await provider.get_earnings_date("SPY")
    assert result is None


@pytest.mark.asyncio
async def test_mock_earnings_confirmed():
    provider = MockEarningsProvider()
    result = await provider.get_earnings_date("AAPL")
    assert result is not None
    assert result.confidence == "CONFIRMED"
    assert result.ticker == "AAPL"


@pytest.mark.asyncio
async def test_mock_earnings_health():
    provider = MockEarningsProvider()
    meta = await provider.health_check()
    assert meta.confidence_score == 1.0
    assert meta.error_details is None


@pytest.mark.asyncio
async def test_mock_price_current():
    provider = MockPriceProvider()
    result = await provider.get_current_price("AAPL")
    assert result is not None
    assert result.ticker == "AAPL"
    assert result.close > 0
    assert result.volume > 0


@pytest.mark.asyncio
async def test_mock_price_unknown_ticker():
    provider = MockPriceProvider()
    result = await provider.get_current_price("ZZZZ")
    assert result is None


@pytest.mark.asyncio
async def test_mock_price_history():
    provider = MockPriceProvider()
    start = date.today() - timedelta(days=30)
    end = date.today()
    results = await provider.get_price_history("MSFT", start, end)
    assert len(results) > 0
    for r in results:
        assert r.ticker == "MSFT"
        assert r.close > 0


@pytest.mark.asyncio
async def test_mock_options_chain():
    provider = MockOptionsProvider()
    chain = await provider.get_options_chain("NVDA")
    assert chain.ticker == "NVDA"
    assert chain.spot_price > 0
    assert len(chain.options) > 0
    assert len(chain.expirations) > 0
    has_call = any(o.option_type == "CALL" for o in chain.options)
    has_put = any(o.option_type == "PUT" for o in chain.options)
    assert has_call
    assert has_put
    for o in chain.options:
        assert o.strike > 0
        if o.bid is not None and o.ask is not None:
            assert o.ask >= o.bid


@pytest.mark.asyncio
async def test_mock_options_expirations():
    provider = MockOptionsProvider()
    exps = await provider.get_expirations("AAPL")
    assert len(exps) > 0
    for e in exps:
        assert e > date.today()


@pytest.mark.asyncio
async def test_mock_volatility_known_ticker():
    provider = MockVolatilityProvider()
    result = await provider.get_volatility_metrics("TSLA")
    assert result.ticker == "TSLA"
    assert result.realized_vol_10d is not None
    assert result.realized_vol_10d > 0
    assert result.iv_rank is not None
    assert result.front_expiry_iv is not None
    assert result.back_expiry_iv is not None
    assert result.term_structure_slope is not None
    assert result.meta.confidence_score > 0


@pytest.mark.asyncio
async def test_mock_volatility_unknown_ticker():
    provider = MockVolatilityProvider()
    result = await provider.get_volatility_metrics("ZZZZ")
    assert result.meta.confidence_score == 0.0
    assert result.meta.error_details is not None


@pytest.mark.asyncio
async def test_mock_volatility_health():
    provider = MockVolatilityProvider()
    meta = await provider.health_check()
    assert meta.confidence_score == 1.0
