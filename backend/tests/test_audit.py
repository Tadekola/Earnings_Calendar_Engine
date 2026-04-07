"""Tests for audit logging service."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import Base
from app.models.audit import AuditLog
from app.services.audit import AuditService


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
async def test_log_generic_event(db_session):
    svc = AuditService(db_session)
    await svc.log("test_event", payload={"key": "value"})
    await db_session.flush()

    result = await db_session.execute(select(AuditLog))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == "test_event"
    assert json.loads(rows[0].payload) == {"key": "value"}


@pytest.mark.asyncio
async def test_log_setting_change(db_session):
    svc = AuditService(db_session)
    await svc.log_setting_change("recommend_threshold", 70, 80)
    await db_session.flush()

    result = await db_session.execute(select(AuditLog))
    row = result.scalars().first()
    assert row.event_type == "setting_changed"
    payload = json.loads(row.payload)
    assert payload["key"] == "recommend_threshold"
    assert payload["new_value"] == "80"


@pytest.mark.asyncio
async def test_log_scan_trigger(db_session):
    svc = AuditService(db_session)
    await svc.log_scan_trigger("api", ["AAPL", "MSFT"])
    await db_session.flush()

    result = await db_session.execute(select(AuditLog))
    row = result.scalars().first()
    assert row.event_type == "scan_triggered"
    payload = json.loads(row.payload)
    assert payload["source"] == "api"
    assert payload["tickers"] == ["AAPL", "MSFT"]


@pytest.mark.asyncio
async def test_log_scan_complete(db_session):
    svc = AuditService(db_session)
    await svc.log_scan_complete("run-123", 10, 3)
    await db_session.flush()

    result = await db_session.execute(select(AuditLog))
    row = result.scalars().first()
    assert row.event_type == "scan_completed"
    assert row.scan_run_id == "run-123"
    payload = json.loads(row.payload)
    assert payload["total"] == 10
    assert payload["recommended"] == 3
