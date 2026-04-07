from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.enums import RecommendationClass, ScanStage
from app.db.session import Base
from app.models.scan import CandidateScore, ScanResult, ScanRun
from app.providers.registry import ProviderRegistry
from app.services.scan_persistence import ScanPersistenceService
from app.services.scan_pipeline import ScanPipeline


@pytest.fixture
async def db_session():
    """Create an in-memory SQLite DB with all tables for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def pipeline():
    settings = get_settings()
    settings.data.ALLOW_SIMULATION = True
    registry = ProviderRegistry(settings)
    registry.initialize()
    return ScanPipeline(settings, registry)


@pytest.mark.asyncio
async def test_save_scan_run(db_session, pipeline):
    scan_result = await pipeline.run(["AAPL", "MSFT"])
    persistence = ScanPersistenceService(db_session)
    db_id = await persistence.save_scan_run(scan_result)

    assert db_id > 0


@pytest.mark.asyncio
async def test_scan_run_stored_in_db(db_session, pipeline):
    scan_result = await pipeline.run(["AAPL"])
    persistence = ScanPersistenceService(db_session)
    await persistence.save_scan_run(scan_result)

    run = await persistence.get_latest_run()
    assert run is not None
    assert run.run_id == scan_result.run_id
    assert run.status == "COMPLETED"
    assert run.total_scanned == 1


@pytest.mark.asyncio
async def test_ticker_results_stored(db_session, pipeline):
    scan_result = await pipeline.run(["AAPL", "MSFT", "NVDA"])
    persistence = ScanPersistenceService(db_session)
    await persistence.save_scan_run(scan_result)

    results = await persistence.get_run_results(scan_result.run_id)
    assert len(results) == 3
    tickers = {r.ticker for r in results}
    assert "AAPL" in tickers


@pytest.mark.asyncio
async def test_candidate_scores_stored(db_session, pipeline):
    scan_result = await pipeline.run(["AAPL", "MSFT"])
    persistence = ScanPersistenceService(db_session)
    await persistence.save_scan_run(scan_result)

    scores = await persistence.get_candidate_scores(scan_result.run_id)
    # Only tickers that passed scoring should have scores
    for score in scores:
        assert score.weighted_total > 0
        assert score.scoring_version != ""
        assert score.score_details_json is not None


@pytest.mark.asyncio
async def test_rejection_stored_correctly(db_session, pipeline):
    # SPY and QQQ have no earnings date → should be rejected
    scan_result = await pipeline.run(["SPY"])
    persistence = ScanPersistenceService(db_session)
    await persistence.save_scan_run(scan_result)

    results = await persistence.get_run_results(scan_result.run_id)
    assert len(results) == 1
    assert results[0].classification == RecommendationClass.NO_TRADE.value
    assert results[0].rejection_reasons is not None


@pytest.mark.asyncio
async def test_multiple_runs_latest(db_session, pipeline):
    persistence = ScanPersistenceService(db_session)

    r1 = await pipeline.run(["AAPL"])
    await persistence.save_scan_run(r1)

    r2 = await pipeline.run(["MSFT"])
    await persistence.save_scan_run(r2)

    latest = await persistence.get_latest_run()
    assert latest is not None
    assert latest.run_id == r2.run_id
