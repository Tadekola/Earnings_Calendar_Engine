from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.enums import RecommendationClass, ScanStage
from app.providers.registry import ProviderRegistry
from app.services.scan_pipeline import ScanPipeline


@pytest.fixture
def pipeline():
    settings = get_settings()
    settings.data.ALLOW_SIMULATION = True
    registry = ProviderRegistry(settings)
    registry.initialize()
    return ScanPipeline(settings, registry)


@pytest.mark.asyncio
async def test_full_scan_runs(pipeline):
    result = await pipeline.run()
    assert result.status == "COMPLETED"
    assert result.total_scanned > 0
    assert result.total_scanned == (
        result.total_recommended + result.total_watchlist + result.total_rejected
    )
    assert len(result.results) == result.total_scanned


@pytest.mark.asyncio
async def test_scan_custom_tickers(pipeline):
    result = await pipeline.run(["AAPL", "MSFT"])
    assert result.total_scanned == 2
    tickers = [r.ticker for r in result.results]
    assert "AAPL" in tickers
    assert "MSFT" in tickers


@pytest.mark.asyncio
async def test_results_sorted_by_score(pipeline):
    result = await pipeline.run()
    scores = [r.overall_score or 0 for r in result.results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_scored_results_have_factors(pipeline):
    result = await pipeline.run(["AAPL"])
    for r in result.results:
        if r.stage_reached == ScanStage.SCORING:
            assert r.scoring_result is not None
            if r.strategy_type == "DOUBLE_CALENDAR":
                assert len(r.scoring_result.factors) >= 9
            else:
                assert len(r.scoring_result.factors) >= 8
            assert r.overall_score is not None
            assert r.overall_score > 0


@pytest.mark.asyncio
async def test_rejected_results_have_reasons(pipeline):
    result = await pipeline.run()
    for r in result.results:
        if (
            r.classification == RecommendationClass.NO_TRADE
            and r.stage_reached != ScanStage.SCORING
        ):
            assert len(r.rejection_reasons) > 0


@pytest.mark.asyncio
async def test_etf_rejected_no_earnings(pipeline):
    result = await pipeline.run(["SPY"])
    assert len(result.results) == 1
    spy = result.results[0]
    assert spy.classification == RecommendationClass.NO_TRADE
    assert spy.stage_reached == ScanStage.EARNINGS_ELIGIBILITY


@pytest.mark.asyncio
async def test_unknown_ticker_rejected(pipeline):
    result = await pipeline.run(["ZZZZ"])
    assert len(result.results) == 1
    assert result.results[0].classification == RecommendationClass.NO_TRADE


@pytest.mark.asyncio
async def test_processing_time_recorded(pipeline):
    result = await pipeline.run(["AAPL"])
    for r in result.results:
        assert r.processing_time_ms >= 0
