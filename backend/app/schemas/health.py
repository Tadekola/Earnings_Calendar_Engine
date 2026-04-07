from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.core.enums import HealthSeverity


class ProviderHealthResponse(BaseModel):
    provider: str
    source_name: str
    is_connected: bool
    confidence_score: float
    freshness_timestamp: datetime | None = None
    latency_ms: int | None = None
    error_details: str | None = None
    severity: HealthSeverity


class HealthResponse(BaseModel):
    status: HealthSeverity
    environment: str
    operating_mode: str
    timestamp: datetime
    version: str = "0.1.0"
    providers: list[ProviderHealthResponse] = []
    database_connected: bool = False
    message: str | None = None


class LivenessResponse(BaseModel):
    status: str = "alive"
    timestamp: datetime


class ReadinessResponse(BaseModel):
    status: str
    timestamp: datetime
    checks: dict[str, bool] = {}
