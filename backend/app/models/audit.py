from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RejectionLog(Base):
    __tablename__ = "rejection_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    metric_name: Mapped[str | None] = mapped_column(String(100))
    metric_value: Mapped[float | None] = mapped_column(Float)
    threshold_value: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ticker: Mapped[str | None] = mapped_column(String(10))
    payload: Mapped[str | None] = mapped_column(Text)
    provider_source: Mapped[str | None] = mapped_column(String(50))
    data_freshness: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config_hash: Mapped[str | None] = mapped_column(String(64))
    scoring_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemHealthSnapshot(Base):
    __tablename__ = "system_health_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_connected: Mapped[bool] = mapped_column(default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    last_successful_fetch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_freshness_seconds: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
