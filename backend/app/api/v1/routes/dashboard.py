"""Dashboard summary API — aggregates recent scan stats and top candidates."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.scan import CandidateScore, ScanResult, ScanRun

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class TopCandidate(BaseModel):
    ticker: str
    score: float
    classification: str
    scan_run_id: str
    strategy_type: str | None = None
    scanned_at: datetime | None = None


class RecentScan(BaseModel):
    run_id: str
    status: str
    total_scanned: int
    total_recommended: int
    total_watchlist: int
    total_rejected: int
    started_at: datetime
    completed_at: datetime | None = None


class DashboardSummary(BaseModel):
    total_scans: int
    total_candidates_scanned: int
    total_recommendations: int
    total_watchlist: int
    avg_score: float | None
    recent_scans: list[RecentScan]
    top_candidates: list[TopCandidate]
    last_scan_at: datetime | None


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DashboardSummary:
    # Aggregate totals from scan_runs
    totals_stmt = select(
        func.count(ScanRun.id).label("total_scans"),
        func.coalesce(func.sum(ScanRun.total_scanned), 0).label("total_scanned"),
        func.coalesce(func.sum(ScanRun.total_recommended), 0).label("total_rec"),
        func.coalesce(func.sum(ScanRun.total_watchlist), 0).label("total_wl"),
        func.max(ScanRun.started_at).label("last_scan"),
    )
    totals = (await db.execute(totals_stmt)).one()

    # Recent scans (last 5)
    recent_stmt = select(ScanRun).order_by(ScanRun.started_at.desc()).limit(5)
    recent_rows = (await db.execute(recent_stmt)).scalars().all()
    recent_scans = [
        RecentScan(
            run_id=r.run_id,
            status=r.status,
            total_scanned=r.total_scanned,
            total_recommended=r.total_recommended,
            total_watchlist=r.total_watchlist,
            total_rejected=r.total_rejected,
            started_at=r.started_at,
            completed_at=r.completed_at,
        )
        for r in recent_rows
    ]

    # Top candidates: highest-scoring from the most recent scan
    top_candidates: list[TopCandidate] = []
    if recent_rows:
        latest_run_id = recent_rows[0].run_id
        top_stmt = (
            select(ScanResult)
            .where(
                ScanResult.scan_run_id == latest_run_id,
                ScanResult.classification.in_(["RECOMMEND", "WATCHLIST"]),
            )
            .order_by(ScanResult.overall_score.desc())
            .limit(10)
        )
        top_rows = (await db.execute(top_stmt)).scalars().all()
        top_candidates = [
            TopCandidate(
                ticker=r.ticker,
                score=r.overall_score or 0.0,
                classification=r.classification,
                scan_run_id=r.scan_run_id,
                strategy_type=r.strategy_type,
                scanned_at=r.created_at,
            )
            for r in top_rows
        ]

    # Average score across all candidates
    avg_stmt = select(func.avg(CandidateScore.weighted_total))
    avg_result = (await db.execute(avg_stmt)).scalar()

    return DashboardSummary(
        total_scans=totals.total_scans or 0,
        total_candidates_scanned=totals.total_scanned or 0,
        total_recommendations=totals.total_rec or 0,
        total_watchlist=totals.total_wl or 0,
        avg_score=round(avg_result, 2) if avg_result else None,
        recent_scans=recent_scans,
        top_candidates=top_candidates,
        last_scan_at=totals.last_scan,
    )


class AuditEntry(BaseModel):
    id: int
    event_type: str
    scan_run_id: str | None = None
    ticker: str | None = None
    payload: str | None = None
    created_at: datetime | None = None


@router.get("/audit", response_model=list[AuditEntry])
async def get_audit_log(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
) -> list[AuditEntry]:
    """Return recent audit log entries."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        AuditEntry(
            id=r.id,
            event_type=r.event_type,
            scan_run_id=r.scan_run_id,
            ticker=r.ticker,
            payload=r.payload,
            created_at=r.created_at,
        )
        for r in rows
    ]
