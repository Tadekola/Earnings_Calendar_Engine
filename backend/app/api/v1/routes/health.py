from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.core.enums import HealthSeverity
from app.schemas.health import (
    HealthResponse,
    LivenessResponse,
    ProviderHealthResponse,
    ReadinessResponse,
)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(request: Request) -> HealthResponse:
    registry = request.app.state.provider_registry
    settings = request.app.state.settings
    now = datetime.now(timezone.utc)

    provider_statuses = await registry.health_check_all()
    providers: list[ProviderHealthResponse] = []
    overall_severity = HealthSeverity.HEALTHY

    for name, meta in provider_statuses.items():
        if meta.error_details:
            severity = HealthSeverity.CRITICAL
            overall_severity = HealthSeverity.CRITICAL
        elif meta.confidence_score < 0.5:
            severity = HealthSeverity.DEGRADED
            if overall_severity != HealthSeverity.CRITICAL:
                overall_severity = HealthSeverity.DEGRADED
        else:
            severity = HealthSeverity.HEALTHY

        providers.append(
            ProviderHealthResponse(
                provider=name,
                source_name=meta.source_name,
                is_connected=meta.error_details is None,
                confidence_score=meta.confidence_score,
                freshness_timestamp=meta.freshness_timestamp,
                error_details=meta.error_details,
                severity=severity,
            )
        )

    return HealthResponse(
        status=overall_severity,
        environment=settings.ENVIRONMENT.value,
        operating_mode=settings.OPERATING_MODE.value,
        timestamp=now,
        providers=providers,
        database_connected=True,
    )


@router.get("/health/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse(timestamp=datetime.now(timezone.utc))


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> ReadinessResponse:
    registry = request.app.state.provider_registry
    provider_statuses = await registry.health_check_all()
    checks = {
        name: meta.error_details is None for name, meta in provider_statuses.items()
    }
    checks["database"] = True
    all_ready = all(checks.values())
    return ReadinessResponse(
        status="ready" if all_ready else "not_ready",
        timestamp=datetime.now(timezone.utc),
        checks=checks,
    )


@router.get("/health/adapters")
async def adapter_health(request: Request) -> dict:
    registry = request.app.state.provider_registry
    provider_statuses = await registry.health_check_all()
    return {
        name: {
            "source": meta.source_name,
            "connected": meta.error_details is None,
            "confidence": meta.confidence_score,
            "freshness": meta.freshness_timestamp.isoformat() if meta.freshness_timestamp else None,
            "error": meta.error_details,
        }
        for name, meta in provider_statuses.items()
    }
