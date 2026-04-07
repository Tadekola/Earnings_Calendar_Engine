from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.session import get_session_factory
from app.providers.registry import ProviderRegistry
from app.services.scan_persistence import ScanPersistenceService
from app.services.scan_pipeline import ScanPipeline

logger = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def scheduled_scan(settings: Settings, registry: ProviderRegistry) -> None:
    """Run a scan and persist results. Called by APScheduler."""
    logger.info("scheduled_scan_starting")
    try:
        pipeline = ScanPipeline(settings, registry)
        result = await pipeline.run()

        factory = get_session_factory()
        async with factory() as session:
            try:
                persistence = ScanPersistenceService(session)
                await persistence.save_scan_run(result)
                await session.commit()
                logger.info(
                    "scheduled_scan_persisted",
                    run_id=result.run_id,
                    recommended=result.total_recommended,
                    watchlist=result.total_watchlist,
                    rejected=result.total_rejected,
                )
            except Exception as e:
                await session.rollback()
                logger.warning("scheduled_scan_persist_failed", error=str(e))

        logger.info(
            "scheduled_scan_completed",
            run_id=result.run_id,
            total=result.total_scanned,
        )
    except Exception as e:
        logger.error("scheduled_scan_failed", error=str(e))


def start_scheduler(settings: Settings, registry: ProviderRegistry) -> AsyncIOScheduler:
    """Start the APScheduler with a daily scan job."""
    global _scheduler

    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler()

    # Run scans at 6:00 AM ET (11:00 UTC) on weekdays — before market open
    _scheduler.add_job(
        scheduled_scan,
        trigger=CronTrigger(day_of_week="mon-fri", hour=11, minute=0),
        args=[settings, registry],
        id="daily_scan",
        name="Daily Pre-market Scan",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Also run at 4:30 PM ET (21:30 UTC) on weekdays — after market close
    _scheduler.add_job(
        scheduled_scan,
        trigger=CronTrigger(day_of_week="mon-fri", hour=21, minute=30),
        args=[settings, registry],
        id="evening_scan",
        name="Evening Post-market Scan",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info("scheduler_started", jobs=len(_scheduler.get_jobs()))
    return _scheduler


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
        _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler
