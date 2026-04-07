from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.scan import (
    ScanRequest,
    ScanResultResponse,
    ScanRunResponse,
    ScanSummaryResponse,
    ScoreBreakdown,
)
from app.services.scan_persistence import ScanPersistenceService
from app.services.scan_pipeline import ScanPipeline

router = APIRouter(prefix="/scan", tags=["scan"])

_scan_store: dict[str, ScanRunResponse] = {}


@router.post("/run", response_model=ScanRunResponse)
async def run_scan(
    request: Request,
    body: ScanRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> ScanRunResponse:
    settings = request.app.state.settings
    registry = request.app.state.provider_registry
    tickers = (body.tickers if body and body.tickers else None)

    from app.services.ws_manager import scan_ws_manager

    pipeline = ScanPipeline(settings, registry)
    scan_result = await pipeline.run(tickers, progress_callback=scan_ws_manager.broadcast)

    # Persist to database (best-effort — don't fail the scan if DB is unavailable)
    try:
        persistence = ScanPersistenceService(db)
        await persistence.save_scan_run(scan_result)

        from app.services.audit import AuditService
        audit = AuditService(db)
        await audit.log_scan_trigger("api", tickers)
        await audit.log_scan_complete(
            scan_result.run_id, scan_result.total_scanned, scan_result.total_recommended,
        )
    except Exception as e:
        import structlog
        structlog.get_logger().warning("scan_persist_failed", error=str(e))
        try:
            await db.rollback()
        except Exception:
            pass

    results: list[ScanResultResponse] = []
    for r in scan_result.results:
        score_breakdown = None
        if r.scoring_result and r.scoring_result.factors:
            score_breakdown = [
                ScoreBreakdown(
                    factor=f.name,
                    weight=f.weight,
                    raw_score=f.raw_score,
                    weighted_score=f.weighted_score,
                    rationale=f.rationale,
                )
                for f in r.scoring_result.factors
            ]

        results.append(ScanResultResponse(
            ticker=r.ticker,
            classification=r.classification,
            overall_score=r.overall_score,
            stage_reached=r.stage_reached.value,
            rejection_reasons=r.rejection_reasons or None,
            rationale_summary=r.rationale_summary,
            processing_time_ms=r.processing_time_ms,
            score_breakdown=score_breakdown,
            risk_warnings=r.scoring_result.risk_warnings if r.scoring_result else None,
        ))

    run = ScanRunResponse(
        run_id=scan_result.run_id,
        status=scan_result.status,
        total_scanned=scan_result.total_scanned,
        total_recommended=scan_result.total_recommended,
        total_watchlist=scan_result.total_watchlist,
        total_rejected=scan_result.total_rejected,
        operating_mode=scan_result.operating_mode,
        scoring_version=scan_result.scoring_version,
        started_at=scan_result.started_at,
        completed_at=scan_result.completed_at,
        results=results,
    )
    _scan_store[scan_result.run_id] = run
    return run


@router.get("/results", response_model=list[ScanSummaryResponse])
async def get_scan_results(db: AsyncSession = Depends(get_db)) -> list[ScanSummaryResponse]:
    # Try DB first, fall back to in-memory store
    try:
        from sqlalchemy import select
        from app.models.scan import ScanRun
        stmt = select(ScanRun).order_by(ScanRun.started_at.desc()).limit(20)
        result = await db.execute(stmt)
        rows = result.scalars().all()
        if rows:
            return [
                ScanSummaryResponse(
                    run_id=r.run_id,
                    status=r.status,
                    total_scanned=r.total_scanned,
                    total_recommended=r.total_recommended,
                    total_watchlist=r.total_watchlist,
                    total_rejected=r.total_rejected,
                    started_at=r.started_at,
                    completed_at=r.completed_at,
                )
                for r in rows
            ]
    except Exception:
        pass

    return [
        ScanSummaryResponse(
            run_id=r.run_id,
            status=r.status,
            total_scanned=r.total_scanned,
            total_recommended=r.total_recommended,
            total_watchlist=r.total_watchlist,
            total_rejected=r.total_rejected,
            started_at=r.started_at,
            completed_at=r.completed_at,
        )
        for r in _scan_store.values()
    ]
