"""Tests for settings persistence service."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.session import Base
from app.services.settings_persistence import SettingsPersistenceService


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_save_and_load_overrides(db_session):
    svc = SettingsPersistenceService(db_session)
    count = await svc.save_overrides({
        "recommend_threshold": 75,
        "watchlist_threshold": 50,
    })
    await db_session.commit()
    assert count == 2

    overrides = await svc.load_overrides()
    assert overrides["recommend_threshold"] == "75"
    assert overrides["watchlist_threshold"] == "50"


@pytest.mark.asyncio
async def test_update_existing_override(db_session):
    svc = SettingsPersistenceService(db_session)
    await svc.save_overrides({"recommend_threshold": 70})
    await db_session.commit()

    await svc.save_overrides({"recommend_threshold": 80})
    await db_session.commit()

    overrides = await svc.load_overrides()
    assert overrides["recommend_threshold"] == "80"


@pytest.mark.asyncio
async def test_apply_overrides_to_settings(db_session):
    settings = get_settings()
    original = settings.scoring.RECOMMEND_THRESHOLD

    svc = SettingsPersistenceService(db_session)
    svc.apply_overrides(settings, {"recommend_threshold": "85"})

    assert settings.scoring.RECOMMEND_THRESHOLD == 85

    # Restore
    settings.scoring.RECOMMEND_THRESHOLD = original


@pytest.mark.asyncio
async def test_ignore_unknown_keys(db_session):
    svc = SettingsPersistenceService(db_session)
    count = await svc.save_overrides({
        "unknown_key": "value",
        "recommend_threshold": 60,
    })
    assert count == 1


@pytest.mark.asyncio
async def test_ignore_none_values(db_session):
    svc = SettingsPersistenceService(db_session)
    count = await svc.save_overrides({
        "recommend_threshold": None,
        "watchlist_threshold": 55,
    })
    assert count == 1


@pytest.mark.asyncio
async def test_apply_int_coercion(db_session):
    settings = get_settings()
    original = settings.earnings_window.MIN_DAYS_TO_EARNINGS

    svc = SettingsPersistenceService(db_session)
    svc.apply_overrides(settings, {"min_days_to_earnings": "10"})

    assert settings.earnings_window.MIN_DAYS_TO_EARNINGS == 10

    # Restore
    settings.earnings_window.MIN_DAYS_TO_EARNINGS = original
