from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_upcoming_earnings(client):
    response = await client.get("/api/v1/earnings/upcoming")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "earnings" in data
    assert isinstance(data["earnings"], list)


@pytest.mark.asyncio
async def test_run_scan(client):
    response = await client.post("/api/v1/scan/run", json={})
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "COMPLETED"
    assert data["total_scanned"] > 0
    assert "results" in data
    for result in data["results"]:
        assert result["classification"] in ("RECOMMEND", "WATCHLIST", "NO_TRADE")
        assert "ticker" in result
        assert "stage_reached" in result


@pytest.mark.asyncio
async def test_scan_results(client):
    response = await client.get("/api/v1/scan/results")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_candidate_detail(client):
    response = await client.get("/api/v1/candidates/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_candidate_not_found(client):
    response = await client.get("/api/v1/candidates/ZZZZZ")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_recommended_trade(client):
    response = await client.get("/api/v1/trades/AAPL/recommended")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert "legs" in data
    assert len(data["legs"]) == 4
    assert "risk_disclaimer" in data
    assert data["risk_disclaimer"] != ""
    for leg in data["legs"]:
        assert leg["option_type"] in ("CALL", "PUT")
        assert leg["side"] in ("BUY", "SELL")


@pytest.mark.asyncio
async def test_build_trade(client):
    response = await client.post("/api/v1/trades/build", json={"ticker": "MSFT"})
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "MSFT"


@pytest.mark.asyncio
async def test_explain_ticker(client):
    response = await client.get("/api/v1/explain/NVDA")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "NVDA"
    assert "factors" in data
    assert "risk_warnings" in data
    assert len(data["risk_warnings"]) > 0


# Removed test_explain_not_found as we now allow any ticker


@pytest.mark.asyncio
async def test_universe(client):
    response = await client.get("/api/v1/universe")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert "tickers" in data
    tickers = [t["ticker"] for t in data["tickers"]]
    assert "AAPL" in tickers
    assert "MSFT" in tickers


@pytest.mark.asyncio
async def test_settings(client):
    response = await client.get("/api/v1/settings")
    assert response.status_code == 200
    data = response.json()
    assert "operating_mode" in data
    assert "scoring" in data
    assert "liquidity" in data
    assert "earnings_window" in data
    assert "universe_tickers" in data


@pytest.mark.asyncio
async def test_rejections(client):
    response = await client.get("/api/v1/rejections")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
    data = response.json()
    assert "total" in data
    assert "rejections" in data
