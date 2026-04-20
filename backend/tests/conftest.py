from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.session import Base, get_db
from app.main import create_app
from app.providers.registry import ProviderRegistry


@pytest.fixture
async def _test_db_engine():
    """Ephemeral in-memory SQLite engine for a single test.

    Tests that call endpoints through the `client` fixture must NOT write to
    the production DB (data/earnings_engine.db). Without this override,
    every `POST /api/v1/scan/run` test would persist a mock-provider scan
    result to the real DB — those millisecond-fast scans pollute the
    "latest scan" lookups used by /candidates and /explain and make the
    UI display bogus classifications for real tickers.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def app(_test_db_engine):
    application = create_app()
    settings = get_settings()
    # Force mock providers in tests regardless of .env API keys
    settings.data.ALLOW_SIMULATION = True
    registry = ProviderRegistry(settings)
    registry.initialize()
    application.state.settings = settings
    application.state.provider_registry = registry

    # Override get_db so any endpoint called through the ASGI client reads
    # from the ephemeral in-memory DB instead of production SQLite.
    factory = async_sessionmaker(
        _test_db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db] = _override_get_db
    try:
        yield application
    finally:
        application.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
