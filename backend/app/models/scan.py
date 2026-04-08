from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    universe_hash: Mapped[str | None] = mapped_column(String(64))
    config_hash: Mapped[str | None] = mapped_column(String(64))
    scoring_version: Mapped[str] = mapped_column(String(20), nullable=False)
    total_scanned: Mapped[int] = mapped_column(Integer, default=0)
    total_recommended: Mapped[int] = mapped_column(Integer, default=0)
    total_watchlist: Mapped[int] = mapped_column(Integer, default=0)
    total_rejected: Mapped[int] = mapped_column(Integer, default=0)
    operating_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class ScanResult(Base):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    stage_reached: Mapped[str] = mapped_column(String(50), nullable=False)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    overall_score: Mapped[float | None] = mapped_column(Float)
    strategy_type: Mapped[str | None] = mapped_column(String(50))
    rejection_reasons: Mapped[str | None] = mapped_column(Text)
    rationale_summary: Mapped[str | None] = mapped_column(Text)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CandidateScore(Base):
    __tablename__ = "candidate_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    liquidity_score: Mapped[float] = mapped_column(Float, nullable=False)
    earnings_timing_score: Mapped[float] = mapped_column(Float, nullable=False)
    vol_term_structure_score: Mapped[float] = mapped_column(Float, nullable=False)
    containment_score: Mapped[float] = mapped_column(Float, nullable=False)
    pricing_efficiency_score: Mapped[float] = mapped_column(Float, nullable=False)
    event_cleanliness_score: Mapped[float] = mapped_column(Float, nullable=False)
    historical_fit_score: Mapped[float] = mapped_column(Float, nullable=False)
    weighted_total: Mapped[float] = mapped_column(Float, nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(20), nullable=False)
    score_details_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
