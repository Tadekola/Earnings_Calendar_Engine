from __future__ import annotations

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

    tz = "America/Chicago"

    # Shared options:
    #   misfire_grace_time=60 — if a backend restart happens >60s after a
    #     scheduled trigger, the missed job is DROPPED (not re-fired). This
    #     prevents restart-time "catch-up" scans from reusing stale in-memory
    #     provider caches and polluting the DB with bogus millisecond scans.
    #   coalesce=True — if multiple triggers pile up, collapse into one fire.
    common_opts = {
        "replace_existing": True,
        "misfire_grace_time": 60,
        "coalesce": True,
    }

    # Pre-market: 7:00 AM CT — catch overnight vol changes before open
    _scheduler.add_job(
        scheduled_scan,
        trigger=CronTrigger(timezone=tz, day_of_week="mon-fri", hour=7, minute=0),
        args=[settings, registry],
        id="premarket_scan",
        name="Pre-market Scan",
        **common_opts,
    )

    # Morning: 9:30 AM CT — right at market open
    _scheduler.add_job(
        scheduled_scan,
        trigger=CronTrigger(timezone=tz, day_of_week="mon-fri", hour=9, minute=30),
        args=[settings, registry],
        id="layered_morning_scan",
        name="V4 Layered Morning Scan",
        **common_opts,
    )

    # Midday: 12:30 PM CT — catch intraday vol structure shifts
    _scheduler.add_job(
        scheduled_scan,
        trigger=CronTrigger(timezone=tz, day_of_week="mon-fri", hour=12, minute=30),
        args=[settings, registry],
        id="midday_scan",
        name="Midday Scan",
        **common_opts,
    )

    # Post-market: 3:30 PM CT (4:30 PM ET) — after market close
    _scheduler.add_job(
        scheduled_scan,
        trigger=CronTrigger(timezone=tz, day_of_week="mon-fri", hour=15, minute=30),
        args=[settings, registry],
        id="evening_scan",
        name="Evening Post-market Scan",
        **common_opts,
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
