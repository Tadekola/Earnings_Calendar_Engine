"""End-to-end integration test.

Boots the full app, runs a scan via the API, verifies persistence to an
in-memory SQLite database, checks the explain/rejections/trades/settings
endpoints, and validates the full API contract.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.session import Base
from app.main import create_app
from app.providers.registry import ProviderRegistry


@pytest.fixture
async def e2e_client():
    """Full app client backed by an in-memory SQLite DB with real tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    application = create_app()
    settings = get_settings()
    settings.data.ALLOW_SIMULATION = True
    registry = ProviderRegistry(settings)
    registry.initialize()
    application.state.settings = settings
    application.state.provider_registry = registry

    # Override the get_db dependency to use our in-memory DB
    from app.db.session import get_db

    async def override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await engine.dispose()


# ── Health ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_health(e2e_client):
    r = await e2e_client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("HEALTHY", "DEGRADED")
    assert "providers" in data
    assert "version" in data


# ── Scan → Persist → Retrieve ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_scan_persist_retrieve(e2e_client):
    # 1. Run a scan
    r = await e2e_client.post("/api/v1/scan/run", json={"tickers": ["AAPL", "MSFT", "NVDA"]})
    assert r.status_code == 200
    scan = r.json()
    assert scan["status"] == "COMPLETED"
    assert scan["total_scanned"] == 3
    assert len(scan["results"]) == 3
    run_id = scan["run_id"]

    # 2. Verify results are retrievable
    r = await e2e_client.get("/api/v1/scan/results")
    assert r.status_code == 200
    results = r.json()
    assert len(results) >= 1
    assert any(s["run_id"] == run_id for s in results)

    # 3. Verify each result has expected fields
    for result in scan["results"]:
        assert "ticker" in result
        assert "classification" in result
        assert result["classification"] in ("RECOMMEND", "WATCHLIST", "NO_TRADE")
        assert "stage_reached" in result
        assert "rationale_summary" in result


# ── Scan Result Structure ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_scored_results_have_breakdown(e2e_client):
    r = await e2e_client.post("/api/v1/scan/run", json={"tickers": ["AAPL"]})
    assert r.status_code == 200
    scan = r.json()
    for result in scan["results"]:
        if result["classification"] in ["RECOMMEND", "WATCHLIST"]:
            assert result["overall_score"] is not None
            assert result["overall_score"] >= 40.0
            assert result["score_breakdown"] is not None
            if result.get("strategy_type") == "DOUBLE_CALENDAR":
                assert len(result["score_breakdown"]) == 9
            assert len(result["rationale_summary"]) > 0
            for factor in result["score_breakdown"]:
                assert "factor" in factor
                assert "weight" in factor
                assert "raw_score" in factor


# ── Explain ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_explain(e2e_client):
    r = await e2e_client.get("/api/v1/explain/AAPL")
    assert r.status_code == 200
    data = r.json()
    assert data["ticker"] == "AAPL"
    assert "classification" in data
    assert "factors" in data
    assert "summary" in data


# ── Rejections ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_rejections(e2e_client):
    r = await e2e_client.get("/api/v1/rejections")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "rejections" in data


# ── Trades ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_recommended_trade(e2e_client):
    r = await e2e_client.get("/api/v1/trades/AAPL/recommended")
    assert r.status_code == 200
    trade = r.json()
    assert trade["ticker"] == "AAPL"
    assert "legs" in trade
    assert len(trade["legs"]) == 4  # double calendar = 4 legs
    assert "total_debit_mid" in trade
    assert "risk_disclaimer" in trade
    assert "key_risks" in trade


@pytest.mark.asyncio
async def test_e2e_build_trade(e2e_client):
    r = await e2e_client.post("/api/v1/trades/build", json={"ticker": "MSFT"})
    assert r.status_code == 200
    trade = r.json()
    assert trade["ticker"] == "MSFT"
    assert trade["classification"] in ("RECOMMEND", "WATCHLIST", "NO_TRADE")


# ── Settings ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_settings(e2e_client):
    r = await e2e_client.get("/api/v1/settings")
    assert r.status_code == 200
    data = r.json()
    assert "operating_mode" in data
    assert "scoring" in data
    assert "liquidity" in data
    assert "earnings_window" in data
    assert "universe_tickers" in data


@pytest.mark.asyncio
async def test_e2e_scheduler_status(e2e_client):
    r = await e2e_client.get("/api/v1/settings/scheduler")
    assert r.status_code == 200
    data = r.json()
    assert "running" in data
    assert "jobs" in data


# ── Earnings ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_upcoming_earnings(e2e_client):
    r = await e2e_client.get("/api/v1/earnings/upcoming")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "earnings" in data


# ── Universe ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_universe(e2e_client):
    r = await e2e_client.get("/api/v1/universe")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "tickers" in data


# ── Full Flow ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_full_flow(e2e_client):
    """Complete user flow: scan → inspect top result → get trade."""
    # 1. Scan
    r = await e2e_client.post("/api/v1/scan/run", json={})
    assert r.status_code == 200
    scan = r.json()
    assert scan["total_scanned"] > 0

    # 2. Pick top result
    top = scan["results"][0]
    ticker = top["ticker"]

    # 3. Explain
    r = await e2e_client.get(f"/api/v1/explain/{ticker}")
    assert r.status_code == 200

    # 4. Get recommended trade
    r = await e2e_client.get(f"/api/v1/trades/{ticker}/recommended")
    assert r.status_code == 200
    trade = r.json()
    assert trade["ticker"] == ticker
    assert len(trade["legs"]) == 4


# ── Dashboard ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_dashboard_summary_empty(e2e_client):
    """Dashboard summary works with no scan data."""
    r = await e2e_client.get("/api/v1/dashboard/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_scans"] == 0
    assert data["recent_scans"] == []
    assert data["top_candidates"] == []


@pytest.mark.asyncio
async def test_e2e_export_scans_csv(e2e_client):
    """Export scans CSV returns valid CSV."""
    r = await e2e_client.get("/api/v1/export/scans/csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "run_id" in r.text  # header row


@pytest.mark.asyncio
async def test_e2e_export_candidates_csv(e2e_client):
    """Export candidates CSV returns valid CSV."""
    r = await e2e_client.get("/api/v1/export/candidates/csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]


@pytest.mark.asyncio
async def test_e2e_dashboard_summary_after_scan(e2e_client):
    """Dashboard summary reflects data after a scan."""
    # Run a scan first
    r = await e2e_client.post("/api/v1/scan/run", json={"tickers": ["AAPL", "MSFT"]})
    assert r.status_code == 200

    # Now check dashboard
    r = await e2e_client.get("/api/v1/dashboard/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_scans"] >= 1
    assert data["total_candidates_scanned"] >= 2
    assert len(data["recent_scans"]) >= 1
    assert data["last_scan_at"] is not None


@pytest.mark.asyncio
async def test_e2e_audit_log_empty(e2e_client):
    """Audit log endpoint works with no data."""
    r = await e2e_client.get("/api/v1/dashboard/audit")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_e2e_audit_log_after_scan(e2e_client):
    """Audit log captures scan events."""
    await e2e_client.post("/api/v1/scan/run", json={"tickers": ["AAPL"]})

    r = await e2e_client.get("/api/v1/dashboard/audit")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) >= 1
    event_types = [e["event_type"] for e in entries]
    assert "scan_triggered" in event_types or "scan_completed" in event_types
