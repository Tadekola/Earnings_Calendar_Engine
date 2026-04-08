from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.core.enums import RecommendationClass


class ScanRequest(BaseModel):
    tickers: list[str] | None = None
    force_rescan: bool = False


class ScoreBreakdown(BaseModel):
    factor: str
    weight: float
    raw_score: float
    weighted_score: float
    rationale: str = ""


class ScanResultResponse(BaseModel):
    ticker: str
    classification: RecommendationClass
    overall_score: float | None = None
    stage_reached: str
    rejection_reasons: list[str] | None = None
    rationale_summary: str | None = None
    score_breakdown: list[ScoreBreakdown] | None = None
    risk_warnings: list[str] | None = None
    processing_time_ms: int | None = None
    strategy_type: str | None = None


class ScanRunResponse(BaseModel):
    run_id: str
    status: str
    total_scanned: int
    total_recommended: int
    total_watchlist: int
    total_rejected: int
    operating_mode: str
    scoring_version: str
    started_at: datetime
    completed_at: datetime | None = None
    results: list[ScanResultResponse] = []


class ScanSummaryResponse(BaseModel):
    run_id: str
    status: str
    total_scanned: int
    total_recommended: int
    total_watchlist: int
    total_rejected: int
    started_at: datetime
    completed_at: datetime | None = None
