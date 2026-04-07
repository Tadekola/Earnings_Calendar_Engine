"""Persist and load user setting overrides from the app_settings DB table."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.settings import AppSetting

logger = get_logger(__name__)

# Maps update request fields → (settings attribute path, category, description)
SETTING_MAP: dict[str, tuple[str, str, str]] = {
    "operating_mode": ("OPERATING_MODE", "core", "Operating mode: STRICT or GRACEFUL"),
    "universe_source": ("data.UNIVERSE_SOURCE", "core", "Universe source: STATIC or SP500"),
    "recommend_threshold": ("scoring.RECOMMEND_THRESHOLD", "scoring", "Score threshold for RECOMMEND"),
    "watchlist_threshold": ("scoring.WATCHLIST_THRESHOLD", "scoring", "Score threshold for WATCHLIST"),
    "min_days_to_earnings": ("earnings_window.MIN_DAYS_TO_EARNINGS", "earnings", "Minimum days before earnings"),
    "max_days_to_earnings": ("earnings_window.MAX_DAYS_TO_EARNINGS", "earnings", "Maximum days before earnings"),
    "exit_days_before_earnings": ("earnings_window.EXIT_DAYS_BEFORE_EARNINGS", "earnings", "Days before earnings to exit"),
    "min_avg_stock_volume": ("liquidity.MIN_AVG_STOCK_VOLUME", "liquidity", "Minimum average stock volume"),
    "min_avg_option_volume": ("liquidity.MIN_AVG_OPTION_VOLUME", "liquidity", "Minimum average option volume"),
    "prefilter_enabled": ("prefilter.ENABLED", "prefilter", "Enable SP500 quality pre-filter"),
    "prefilter_min_price": ("prefilter.MIN_STOCK_PRICE", "prefilter", "Min stock price for SP500 pre-filter"),
    "prefilter_min_mktcap_b": ("prefilter.MIN_MARKET_CAP_B", "prefilter", "Min market cap (billions) for SP500 pre-filter"),
    "prefilter_require_weeklies": ("prefilter.REQUIRE_WEEKLY_OPTIONS", "prefilter", "Require weekly options for SP500 pre-filter"),
}


class SettingsPersistenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_overrides(self, overrides: dict[str, Any]) -> int:
        """Save setting overrides to DB. Returns count of saved settings."""
        count = 0
        for key, value in overrides.items():
            if value is None or key not in SETTING_MAP:
                continue

            attr_path, category, description = SETTING_MAP[key]
            str_value = str(value)

            stmt = select(AppSetting).where(AppSetting.key == key)
            result = await self._session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.value = str_value
                existing.updated_at = datetime.now(timezone.utc)
                existing.updated_by = "user"
            else:
                self._session.add(AppSetting(
                    key=key,
                    value=str_value,
                    category=category,
                    description=description,
                    updated_by="user",
                ))
            count += 1

        if count > 0:
            await self._session.flush()
        return count

    async def load_overrides(self) -> dict[str, str]:
        """Load all overrides from DB as key→value strings."""
        stmt = select(AppSetting)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return {r.key: r.value for r in rows}

    def apply_overrides(self, settings: Settings, overrides: dict[str, str]) -> None:
        """Apply DB overrides onto a Settings instance in-memory."""
        for key, raw_value in overrides.items():
            if key not in SETTING_MAP:
                continue
            attr_path, _, _ = SETTING_MAP[key]
            try:
                self._set_nested(settings, attr_path, raw_value)
                logger.debug("setting_override_applied", key=key, value=raw_value)
            except Exception as e:
                logger.warning("setting_override_failed", key=key, error=str(e))

    @staticmethod
    def _set_nested(obj: Any, path: str, raw_value: str) -> None:
        """Set a dotted attribute path on an object, coercing the value."""
        from enum import Enum
        parts = path.split(".")
        target = obj
        for part in parts[:-1]:
            target = getattr(target, part)

        attr_name = parts[-1]
        current = getattr(target, attr_name)

        # Coerce to the same type as the current value
        if isinstance(current, bool):
            coerced: Any = raw_value.lower() in ("true", "1", "yes")
        elif isinstance(current, int):
            coerced = int(raw_value)
        elif isinstance(current, float):
            coerced = float(raw_value)
        elif isinstance(current, Enum):
            coerced = type(current)(raw_value.upper())
        else:
            coerced = raw_value

        setattr(target, attr_name, coerced)
