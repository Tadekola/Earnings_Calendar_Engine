from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class ProviderMeta:
    source_name: str
    freshness_timestamp: datetime | None = None
    confidence_score: float = 0.0
    error_details: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def is_fresh(self) -> bool:
        if self.freshness_timestamp is None:
            return False
        age_seconds = (datetime.now(self.freshness_timestamp.tzinfo) - self.freshness_timestamp).total_seconds()
        return age_seconds < 3600

    @property
    def is_healthy(self) -> bool:
        return self.error_details is None and self.confidence_score > 0.0


@dataclass
class EarningsRecord:
    ticker: str
    earnings_date: date
    report_timing: str = "UNKNOWN"
    confidence: str = "ESTIMATED"
    fiscal_quarter: str | None = None
    fiscal_year: int | None = None
    meta: ProviderMeta = field(default_factory=lambda: ProviderMeta(source_name="unknown"))


@dataclass
class PriceRecord:
    ticker: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    avg_dollar_volume: float | None = None
    meta: ProviderMeta = field(default_factory=lambda: ProviderMeta(source_name="unknown"))


@dataclass
class OptionRecord:
    ticker: str
    option_type: str
    strike: float
    expiration: date
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    last: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None


@dataclass
class OptionsChainSnapshot:
    ticker: str
    spot_price: float
    snapshot_time: datetime
    options: list[OptionRecord] = field(default_factory=list)
    expirations: list[date] = field(default_factory=list)
    meta: ProviderMeta = field(default_factory=lambda: ProviderMeta(source_name="unknown"))


@dataclass
class VolatilitySnapshot:
    ticker: str
    as_of_date: date
    realized_vol_10d: float | None = None
    realized_vol_20d: float | None = None
    realized_vol_30d: float | None = None
    atr_14d: float | None = None
    iv_rank: float | None = None
    iv_percentile: float | None = None
    front_expiry_iv: float | None = None
    back_expiry_iv: float | None = None
    term_structure_slope: float | None = None
    meta: ProviderMeta = field(default_factory=lambda: ProviderMeta(source_name="unknown"))


class EarningsCalendarProvider(ABC):
    @abstractmethod
    async def get_upcoming_earnings(
        self, tickers: list[str], days_ahead: int = 30
    ) -> list[EarningsRecord]:
        ...

    @abstractmethod
    async def get_earnings_date(self, ticker: str) -> EarningsRecord | None:
        ...

    @abstractmethod
    async def health_check(self) -> ProviderMeta:
        ...


class PriceProvider(ABC):
    @abstractmethod
    async def get_current_price(self, ticker: str) -> PriceRecord | None:
        ...

    @abstractmethod
    async def get_price_history(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[PriceRecord]:
        ...

    @abstractmethod
    async def health_check(self) -> ProviderMeta:
        ...


class OptionsChainProvider(ABC):
    @abstractmethod
    async def get_options_chain(
        self, ticker: str, expirations: list[date] | None = None
    ) -> OptionsChainSnapshot:
        ...

    @abstractmethod
    async def get_expirations(self, ticker: str) -> list[date]:
        ...

    @abstractmethod
    async def health_check(self) -> ProviderMeta:
        ...


class VolatilityMetricsProvider(ABC):
    @abstractmethod
    async def get_volatility_metrics(self, ticker: str) -> VolatilitySnapshot:
        ...

    @abstractmethod
    async def health_check(self) -> ProviderMeta:
        ...


class MacroEventProvider(ABC):
    @abstractmethod
    async def get_upcoming_events(self, days_ahead: int = 14) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    async def health_check(self) -> ProviderMeta:
        ...
