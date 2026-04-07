from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.settings import (
    AppSettingsResponse,
    AppSettingsUpdateRequest,
    EarningsWindowSettingsResponse,
    LiquiditySettingsResponse,
    ScoringSettingsResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class ScheduleJobResponse(BaseModel):
    id: str
    name: str
    next_run: str | None = None


class SchedulerStatusResponse(BaseModel):
    running: bool
    jobs: list[ScheduleJobResponse]


@router.get("", response_model=AppSettingsResponse)
async def get_settings(request: Request) -> AppSettingsResponse:
    s = request.app.state.settings
    return AppSettingsResponse(
        operating_mode=s.OPERATING_MODE,
        universe_source=s.data.UNIVERSE_SOURCE,
        scoring=ScoringSettingsResponse(
            liquidity_weight=s.scoring.LIQUIDITY_WEIGHT,
            earnings_timing_weight=s.scoring.EARNINGS_TIMING_WEIGHT,
            vol_term_structure_weight=s.scoring.VOL_TERM_STRUCTURE_WEIGHT,
            containment_weight=s.scoring.CONTAINMENT_WEIGHT,
            pricing_efficiency_weight=s.scoring.PRICING_EFFICIENCY_WEIGHT,
            event_cleanliness_weight=s.scoring.EVENT_CLEANLINESS_WEIGHT,
            historical_fit_weight=s.scoring.HISTORICAL_FIT_WEIGHT,
            recommend_threshold=s.scoring.RECOMMEND_THRESHOLD,
            watchlist_threshold=s.scoring.WATCHLIST_THRESHOLD,
            scoring_version=s.scoring.SCORING_VERSION,
        ),
        liquidity=LiquiditySettingsResponse(
            min_avg_stock_volume=s.liquidity.MIN_AVG_STOCK_VOLUME,
            min_avg_option_volume=s.liquidity.MIN_AVG_OPTION_VOLUME,
            min_open_interest=s.liquidity.MIN_OPEN_INTEREST,
            max_bid_ask_pct=s.liquidity.MAX_BID_ASK_PCT,
            max_bid_ask_abs=s.liquidity.MAX_BID_ASK_ABS,
            max_spread_to_mid=s.liquidity.MAX_SPREAD_TO_MID,
            min_strike_density=s.liquidity.MIN_STRIKE_DENSITY,
        ),
        earnings_window=EarningsWindowSettingsResponse(
            min_days_to_earnings=s.earnings_window.MIN_DAYS_TO_EARNINGS,
            max_days_to_earnings=s.earnings_window.MAX_DAYS_TO_EARNINGS,
            exit_days_before_earnings=s.earnings_window.EXIT_DAYS_BEFORE_EARNINGS,
            require_confirmed_date=s.earnings_window.REQUIRE_CONFIRMED_DATE,
        ),
        universe_tickers=s.DEFAULT_UNIVERSE,
    )


@router.put("", response_model=AppSettingsResponse)
async def update_settings(
    request: Request,
    body: AppSettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> AppSettingsResponse:
    from app.services.settings_persistence import SettingsPersistenceService

    settings = request.app.state.settings
    overrides = body.model_dump(exclude_none=True)

    try:
        svc = SettingsPersistenceService(db)
        count = await svc.save_overrides(overrides)
        if count > 0:
            # Audit log each changed setting
            from app.services.audit import AuditService
            audit = AuditService(db)
            for key, new_val in overrides.items():
                if new_val is not None:
                    await audit.log_setting_change(key, "—", new_val)

            await db.commit()
            # Apply to live settings in-memory
            db_overrides = await svc.load_overrides()
            svc.apply_overrides(settings, db_overrides)
    except Exception as e:
        import structlog
        structlog.get_logger().warning("settings_persist_failed", error=str(e))
        try:
            await db.rollback()
        except Exception:
            pass

    return await get_settings(request)


@router.get("/scheduler", response_model=SchedulerStatusResponse)
async def get_scheduler_status(request: Request) -> SchedulerStatusResponse:
    from app.services.scheduler import get_scheduler
    scheduler = get_scheduler()
    if scheduler is None:
        return SchedulerStatusResponse(running=False, jobs=[])

    jobs = []
    for job in scheduler.get_jobs():
        next_run = None
        if job.next_run_time:
            next_run = job.next_run_time.isoformat()
        jobs.append(ScheduleJobResponse(id=job.id, name=job.name, next_run=next_run))

    return SchedulerStatusResponse(running=scheduler.running, jobs=jobs)


@router.post("/scheduler/trigger")
async def trigger_scan_now(request: Request) -> dict:
    """Manually trigger an immediate scan."""
    from app.services.scheduler import get_scheduler, scheduled_scan
    settings = request.app.state.settings
    registry = request.app.state.provider_registry

    import asyncio
    asyncio.create_task(scheduled_scan(settings, registry))

    return {"status": "triggered", "message": "Scan job started in background"}
