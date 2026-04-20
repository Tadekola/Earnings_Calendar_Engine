from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.v1.routes.health import router as health_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.security import RISK_DISCLAIMER, RequestLoggingMiddleware
from app.db.session import close_db, init_db
from app.providers.registry import ProviderRegistry
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    logger = get_logger("startup")

    logger.info(
        "app_starting",
        environment=settings.ENVIRONMENT.value,
        operating_mode=settings.OPERATING_MODE.value,
    )

    await init_db()
    logger.info("database_initialized")

    registry = ProviderRegistry(settings)
    registry.initialize()
    logger.info("providers_initialized")

    app.state.settings = settings
    app.state.provider_registry = registry

    # Start scheduled scan jobs
    try:
        scheduler = start_scheduler(settings, registry)
        app.state.scheduler = scheduler
    except Exception as e:
        logger.warning("scheduler_start_failed", error=str(e))

    yield

    logger.info("app_shutting_down")
    stop_scheduler()
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Earnings Calendar Engine",
        description=(
            "Pre-earnings Double Calendar Scanner and Builder for liquid U.S. equities. "
            f"{RISK_DISCLAIMER}"
        ),
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.API_PREFIX)

    return app


app = create_app()
