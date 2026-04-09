from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import FMPSettings, TradierSettings
from app.providers.live.fmp import FMPEarningsProvider, FMPPriceProvider
from app.providers.live.tradier import TradierOptionsProvider

# ---------------------------------------------------------------------------
# FMP Earnings Provider
# ---------------------------------------------------------------------------

def _fmp_settings() -> FMPSettings:
    return FMPSettings(FMP_API_KEY="test_key_123", FMP_TIMEOUT=5, FMP_MAX_RETRIES=1)


def _mock_fmp_earnings_response() -> list[dict]:
    today = date.today()
    return [
        {
            "date": (today + timedelta(days=14)).isoformat(),
            "symbol": "AAPL",
            "time": "amc",
            "fiscalDateEnding": f"{today.year}-06-30",
        },
        {
            "date": (today + timedelta(days=10)).isoformat(),
            "symbol": "MSFT",
            "time": "bmo",
            "fiscalDateEnding": f"{today.year}-03-31",
        },
        {
            "date": (today + timedelta(days=20)).isoformat(),
            "symbol": "GOOG",
            "time": "",
            "fiscalDateEnding": None,
        },
    ]


@pytest.mark.asyncio
async def test_fmp_earnings_upcoming():
    provider = FMPEarningsProvider(_fmp_settings())
    mock_resp = httpx.Response(200, json=_mock_fmp_earnings_response())

    with patch.object(provider, "_request", new_callable=AsyncMock, return_value=_mock_fmp_earnings_response()):
        results = await provider.get_upcoming_earnings(["AAPL", "MSFT"], days_ahead=30)

    assert len(results) == 2
    assert results[0].ticker == "MSFT"  # sorted by date, MSFT is 10d out
    assert results[1].ticker == "AAPL"
    assert results[1].report_timing == "AFTER_CLOSE"
    assert results[0].report_timing == "BEFORE_OPEN"


@pytest.mark.asyncio
async def test_fmp_earnings_date_single():
    provider = FMPEarningsProvider(_fmp_settings())

    with patch.object(provider, "_request", new_callable=AsyncMock, return_value=_mock_fmp_earnings_response()):
        rec = await provider.get_earnings_date("AAPL")

    assert rec is not None
    assert rec.ticker == "AAPL"
    assert rec.confidence == "CONFIRMED"


@pytest.mark.asyncio
async def test_fmp_earnings_not_found():
    provider = FMPEarningsProvider(_fmp_settings())

    with patch.object(provider, "_request", new_callable=AsyncMock, return_value=[]):
        rec = await provider.get_earnings_date("ZZZZZ")

    assert rec is None


@pytest.mark.asyncio
async def test_fmp_earnings_api_error():
    provider = FMPEarningsProvider(_fmp_settings())

    with patch.object(provider, "_request", new_callable=AsyncMock, side_effect=httpx.TransportError("timeout")):
        rec = await provider.get_earnings_date("AAPL")

    assert rec is None


@pytest.mark.asyncio
async def test_fmp_earnings_health_ok():
    provider = FMPEarningsProvider(_fmp_settings())

    with patch.object(provider, "_request", new_callable=AsyncMock, return_value=[{"symbol": "AAPL"}]):
        meta = await provider.health_check()

    assert meta.confidence_score > 0
    assert meta.error_details is None


@pytest.mark.asyncio
async def test_fmp_earnings_health_fail():
    provider = FMPEarningsProvider(_fmp_settings())

    with patch.object(provider, "_request", new_callable=AsyncMock, side_effect=Exception("network")):
        meta = await provider.health_check()

    assert meta.confidence_score == 0.0
    assert meta.error_details is not None


# ---------------------------------------------------------------------------
# FMP Price Provider
# ---------------------------------------------------------------------------

def _mock_fmp_quote_response() -> list[dict]:
    return [
        {
            "symbol": "AAPL",
            "price": 195.50,
            "open": 194.0,
            "dayHigh": 196.0,
            "dayLow": 193.5,
            "volume": 55000000,
            "avgVolume": 52000000,
            "previousClose": 194.80,
        }
    ]


@pytest.mark.asyncio
async def test_fmp_price_current():
    provider = FMPPriceProvider(_fmp_settings())

    with patch.object(provider, "_request", new_callable=AsyncMock, return_value=_mock_fmp_quote_response()):
        rec = await provider.get_current_price("AAPL")

    assert rec is not None
    assert rec.ticker == "AAPL"
    assert rec.close == 195.50
    assert rec.volume == 55000000
    assert rec.avg_dollar_volume is not None


@pytest.mark.asyncio
async def test_fmp_price_not_found():
    provider = FMPPriceProvider(_fmp_settings())

    with patch.object(provider, "_request", new_callable=AsyncMock, return_value=[]):
        rec = await provider.get_current_price("ZZZZZ")

    assert rec is None


@pytest.mark.asyncio
async def test_fmp_price_history():
    today = date.today()
    provider = FMPPriceProvider(_fmp_settings())
    mock_data = {
        "symbol": "AAPL",
        "historical": [
            {"date": (today - timedelta(days=2)).isoformat(), "open": 193.0, "high": 195.0, "low": 192.0, "close": 194.0, "volume": 50000000},
            {"date": (today - timedelta(days=1)).isoformat(), "open": 194.0, "high": 196.0, "low": 193.5, "close": 195.5, "volume": 55000000},
        ],
    }

    with patch.object(provider, "_request", new_callable=AsyncMock, return_value=mock_data):
        records = await provider.get_price_history("AAPL", today - timedelta(days=5), today)

    assert len(records) == 2
    assert records[0].trade_date < records[1].trade_date


# ---------------------------------------------------------------------------
# Tradier Options Provider
# ---------------------------------------------------------------------------

def _tradier_settings() -> TradierSettings:
    return TradierSettings(TRADIER_ACCESS_TOKEN="test_token_456", TRADIER_TIMEOUT=5, TRADIER_MAX_RETRIES=1)


@pytest.mark.asyncio
async def test_tradier_expirations():
    provider = TradierOptionsProvider(_tradier_settings())
    mock_data = {
        "expirations": {
            "date": ["2026-04-17", "2026-05-15", "2026-06-19"]
        }
    }

    with patch.object(provider, "_request", new_callable=AsyncMock, return_value=mock_data):
        exps = await provider.get_expirations("AAPL")

    assert len(exps) == 3
    assert exps[0] == date(2026, 4, 17)


@pytest.mark.asyncio
async def test_tradier_chain():
    provider = TradierOptionsProvider(_tradier_settings())
    exp = date(2026, 4, 17)

    exp_data = {"expirations": {"date": [exp.isoformat()]}}
    chain_data = {
        "options": {
            "option": [
                {
                    "option_type": "call",
                    "strike": 195.0,
                    "bid": 5.10,
                    "ask": 5.30,
                    "last": 5.20,
                    "volume": 1200,
                    "open_interest": 5000,
                    "greeks": {"mid_iv": 0.28, "delta": 0.52, "gamma": 0.03, "theta": -0.05, "vega": 0.15, "rho": 0.02},
                },
                {
                    "option_type": "put",
                    "strike": 195.0,
                    "bid": 4.80,
                    "ask": 5.00,
                    "last": 4.90,
                    "volume": 800,
                    "open_interest": 3500,
                    "greeks": {"mid_iv": 0.27, "delta": -0.48, "gamma": 0.03, "theta": -0.04, "vega": 0.14, "rho": -0.01},
                },
            ]
        }
    }
    quote_data = {"quotes": {"quote": {"last": 195.50}}}

    call_count = 0

    async def mock_request(path, params=None):
        nonlocal call_count
        call_count += 1
        if "expirations" in path:
            return exp_data
        elif "chains" in path:
            return chain_data
        elif "quotes" in path:
            return quote_data
        return {}

    with patch.object(provider, "_request", side_effect=mock_request):
        snapshot = await provider.get_options_chain("AAPL")

    assert snapshot.ticker == "AAPL"
    assert snapshot.spot_price == 195.50
    assert len(snapshot.options) == 2
    assert snapshot.options[0].option_type == "call"
    assert snapshot.options[0].strike == 195.0
    assert snapshot.options[0].implied_volatility == 0.28
    assert snapshot.options[0].delta == 0.52
    assert snapshot.options[1].option_type == "put"


@pytest.mark.asyncio
async def test_tradier_chain_empty():
    provider = TradierOptionsProvider(_tradier_settings())

    async def mock_request(path, params=None):
        if "expirations" in path:
            return {"expirations": {"date": []}}
        elif "quotes" in path:
            return {"quotes": {"quote": {"last": 100.0}}}
        return {}

    with patch.object(provider, "_request", side_effect=mock_request):
        snapshot = await provider.get_options_chain("ZZZZZ")

    assert snapshot.ticker == "ZZZZZ"
    assert len(snapshot.options) == 0


@pytest.mark.asyncio
async def test_tradier_health_ok():
    provider = TradierOptionsProvider(_tradier_settings())
    mock_data = {"expirations": {"date": ["2026-04-17"]}}

    with patch.object(provider, "_request", new_callable=AsyncMock, return_value=mock_data):
        meta = await provider.health_check()

    assert meta.confidence_score > 0
    assert meta.error_details is None


@pytest.mark.asyncio
async def test_tradier_health_fail():
    provider = TradierOptionsProvider(_tradier_settings())

    with patch.object(provider, "_request", new_callable=AsyncMock, side_effect=Exception("auth failed")):
        meta = await provider.health_check()

    assert meta.confidence_score == 0.0
    assert "auth failed" in meta.error_details
