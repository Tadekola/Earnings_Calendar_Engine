from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.scan import CandidateScore, ScanResult, ScanRun
from app.services.scan_pipeline import ScanRunResult, TickerScanResult

logger = get_logger(__name__)


class ScanPersistenceService:
    """Persists scan pipeline results to the database."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_scan_run(self, run: ScanRunResult) -> int:
        """Save a complete scan run with all results and scores. Returns the DB id."""
        db_run = ScanRun(
            run_id=run.run_id,
            status=run.status,
            scoring_version=run.scoring_version,
            total_scanned=run.total_scanned,
            total_recommended=run.total_recommended,
            total_watchlist=run.total_watchlist,
            total_rejected=run.total_rejected,
            operating_mode=run.operating_mode,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )
        self._session.add(db_run)
        await self._session.flush()

        for ticker_result in run.results:
            await self._save_ticker_result(run.run_id, ticker_result)

        await self._session.commit()
        logger.info(
            "scan_run_persisted",
            run_id=run.run_id,
            total_results=len(run.results),
        )
        return db_run.id

    async def _save_ticker_result(
        self, run_id: str, result: TickerScanResult
    ) -> None:
        db_result = ScanResult(
            scan_run_id=run_id,
            ticker=result.ticker,
            stage_reached=result.stage_reached.value,
            classification=result.classification.value,
            overall_score=result.overall_score,
            strategy_type=result.strategy_type,
            rejection_reasons="; ".join(result.rejection_reasons) if result.rejection_reasons else None,
            rationale_summary=result.rationale_summary,
            processing_time_ms=result.processing_time_ms,
        )
        self._session.add(db_result)

        # Save detailed score breakdown if scoring was completed
        if result.scoring_result is not None:
            sr = result.scoring_result
            factor_map = {f.name: f for f in sr.factors}

            details = {
                "risk_warnings": sr.risk_warnings,
                "factors": [
                    {
                        "name": f.name,
                        "raw_score": f.raw_score,
                        "weight": f.weight,
                        "weighted_score": f.weighted_score,
                        "rationale": f.rationale,
                    }
                    for f in sr.factors
                ],
            }

            db_score = CandidateScore(
                scan_run_id=run_id,
                ticker=result.ticker,
                liquidity_score=factor_map.get("Liquidity Quality", _dummy()).raw_score,
                earnings_timing_score=factor_map.get("Earnings Timing", _dummy()).raw_score,
                vol_term_structure_score=factor_map.get("Vol Term Structure", _dummy()).raw_score,
                containment_score=factor_map.get("Pre-earnings Containment", _dummy()).raw_score,
                pricing_efficiency_score=factor_map.get("Pricing Efficiency", _dummy()).raw_score,
                event_cleanliness_score=factor_map.get("Event Cleanliness", _dummy()).raw_score,
                historical_fit_score=factor_map.get("Historical Fit", _dummy()).raw_score,
                weighted_total=sr.overall_score,
                scoring_version=sr.scoring_version,
                score_details_json=json.dumps(details),
            )
            self._session.add(db_score)

    async def get_latest_run(self) -> ScanRun | None:
        from sqlalchemy import select
        stmt = select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_run_results(self, run_id: str) -> list[ScanResult]:
        from sqlalchemy import select
        stmt = select(ScanResult).where(ScanResult.scan_run_id == run_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_candidate_scores(self, run_id: str) -> list[CandidateScore]:
        from sqlalchemy import select
        stmt = select(CandidateScore).where(CandidateScore.scan_run_id == run_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class _DummyFactor:
    raw_score: float = 0.0


def _dummy() -> _DummyFactor:
    return _DummyFactor()
