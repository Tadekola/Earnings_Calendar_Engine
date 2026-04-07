"""Audit logging service — records user actions and system events to audit_logs table."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit import AuditLog

logger = get_logger(__name__)


class AuditService:
    """Write audit trail entries to the database."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        event_type: str,
        *,
        scan_run_id: str | None = None,
        ticker: str | None = None,
        payload: dict[str, Any] | None = None,
        provider_source: str | None = None,
        scoring_version: str | None = None,
    ) -> None:
        entry = AuditLog(
            event_type=event_type,
            scan_run_id=scan_run_id,
            ticker=ticker,
            payload=json.dumps(payload) if payload else None,
            provider_source=provider_source,
            scoring_version=scoring_version,
            data_freshness=datetime.now(timezone.utc),
        )
        self._session.add(entry)
        logger.debug("audit_logged", event_type=event_type, ticker=ticker)

    async def log_setting_change(self, key: str, old_value: Any, new_value: Any) -> None:
        await self.log(
            "setting_changed",
            payload={"key": key, "old_value": str(old_value), "new_value": str(new_value)},
        )

    async def log_scan_trigger(self, source: str, tickers: list[str] | None = None) -> None:
        await self.log(
            "scan_triggered",
            payload={"source": source, "tickers": tickers},
        )

    async def log_scan_complete(self, run_id: str, total: int, recommended: int) -> None:
        await self.log(
            "scan_completed",
            scan_run_id=run_id,
            payload={"total": total, "recommended": recommended},
        )
