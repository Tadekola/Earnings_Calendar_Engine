"""CSV export endpoints for scan results and candidates."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.scan import CandidateScore, ScanResult, ScanRun

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/scans/csv")
async def export_scans_csv(db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """Export all scan run summaries as CSV."""
    stmt = select(ScanRun).order_by(ScanRun.started_at.desc()).limit(100)
    rows = (await db.execute(stmt)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "run_id", "status", "total_scanned", "total_recommended",
        "total_watchlist", "total_rejected", "operating_mode",
        "scoring_version", "started_at", "completed_at",
    ])
    for r in rows:
        writer.writerow([
            r.run_id, r.status, r.total_scanned, r.total_recommended,
            r.total_watchlist, r.total_rejected, r.operating_mode,
            r.scoring_version,
            r.started_at.isoformat() if r.started_at else "",
            r.completed_at.isoformat() if r.completed_at else "",
        ])

    buf.seek(0)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="scan_runs_{ts}.csv"'},
    )


@router.get("/candidates/csv")
async def export_candidates_csv(
    run_id: str | None = Query(None, description="Filter by scan run ID"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export scan result candidates as CSV, optionally filtered by run_id."""
    stmt = select(ScanResult).order_by(ScanResult.created_at.desc())
    if run_id:
        stmt = stmt.where(ScanResult.scan_run_id == run_id)
    stmt = stmt.limit(500)
    rows = (await db.execute(stmt)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "scan_run_id", "ticker", "classification", "overall_score",
        "stage_reached", "rejection_reasons", "rationale_summary",
        "processing_time_ms", "created_at",
    ])
    for r in rows:
        writer.writerow([
            r.scan_run_id, r.ticker, r.classification, r.overall_score,
            r.stage_reached, r.rejection_reasons or "", r.rationale_summary or "",
            r.processing_time_ms,
            r.created_at.isoformat() if r.created_at else "",
        ])

    buf.seek(0)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="candidates_{ts}.csv"'},
    )


@router.get("/scores/csv")
async def export_scores_csv(
    run_id: str | None = Query(None, description="Filter by scan run ID"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export candidate score breakdowns as CSV."""
    stmt = select(CandidateScore).order_by(CandidateScore.created_at.desc())
    if run_id:
        stmt = stmt.where(CandidateScore.scan_run_id == run_id)
    stmt = stmt.limit(500)
    rows = (await db.execute(stmt)).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "scan_run_id", "ticker", "liquidity", "earnings_timing",
        "vol_term_structure", "containment", "pricing_efficiency",
        "event_cleanliness", "historical_fit", "weighted_total",
        "scoring_version", "created_at",
    ])
    for r in rows:
        writer.writerow([
            r.scan_run_id, r.ticker,
            r.liquidity_score, r.earnings_timing_score,
            r.vol_term_structure_score, r.containment_score,
            r.pricing_efficiency_score, r.event_cleanliness_score,
            r.historical_fit_score, r.weighted_total,
            r.scoring_version,
            r.created_at.isoformat() if r.created_at else "",
        ])

    buf.seek(0)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="scores_{ts}.csv"'},
    )
