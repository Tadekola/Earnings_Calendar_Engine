from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.core.config import Settings
from app.core.enums import LegSide, OptionType, RecommendationClass
from app.core.logging import get_logger
from app.core.security import RISK_DISCLAIMER
from app.providers.base import (
    EarningsRecord,
    OptionsChainSnapshot,
    OptionRecord,
    PriceRecord,
    VolatilitySnapshot,
)
from app.providers.registry import ProviderRegistry
from app.services.liquidity import LiquidityEngine
from app.services.scoring import ScoringEngine

logger = get_logger(__name__)


@dataclass
class TradeLeg:
    leg_number: int
    option_type: OptionType
    side: LegSide
    strike: float
    expiration: date
    quantity: int = 1
    option: OptionRecord | None = None

    @property
    def bid(self) -> float | None:
        return self.option.bid if self.option else None

    @property
    def ask(self) -> float | None:
        return self.option.ask if self.option else None

    @property
    def mid(self) -> float | None:
        if self.option and self.option.bid is not None and self.option.ask is not None:
            return round((self.option.bid + self.option.ask) / 2, 4)
        return self.option.mid if self.option else None

    @property
    def debit(self) -> float:
        m = self.mid or 0.0
        return m if self.side == LegSide.BUY else -m

    @property
    def spread_to_mid(self) -> float | None:
        if self.option and self.option.bid is not None and self.option.ask is not None:
            mid = (self.option.bid + self.option.ask) / 2
            if mid > 0:
                return round((self.option.ask - self.option.bid) / mid, 4)
        return None


@dataclass
class ConstructedTrade:
    ticker: str
    spot_price: float
    earnings_date: date
    earnings_confidence: str
    entry_date_start: date
    entry_date_end: date
    planned_exit_date: date
    short_expiry: date
    long_expiry: date
    lower_strike: float
    upper_strike: float
    legs: list[TradeLeg]
    total_debit_mid: float
    total_debit_pessimistic: float
    estimated_max_loss: float
    profit_zone_low: float
    profit_zone_high: float
    classification: RecommendationClass = RecommendationClass.WATCHLIST
    overall_score: float = 0.0
    rationale_summary: str = ""
    key_risks: list[str] = field(default_factory=list)
    risk_disclaimer: str = RISK_DISCLAIMER
    strategy_type: str = "DOUBLE_CALENDAR"


class TradeConstructionEngine:
    """
    Backward-compatible facade that delegates trade building to the active strategy.
    In Phase 1, it defaults to the Double Calendar strategy.
    """
    def __init__(self, settings: Settings, registry: ProviderRegistry) -> None:
        self._settings = settings
        self._registry = registry
        
        from app.services.base_strategy import StrategyFactory
        self._strategy = StrategyFactory(settings, registry).get_active_strategies()[0]

    async def build_recommended(self, ticker: str) -> ConstructedTrade:
        earnings = await self._registry.earnings.get_earnings_date(ticker)
        if earnings is None:
            raise ValueError(f"No earnings date for {ticker}")

        price = await self._registry.price.get_current_price(ticker)
        if price is None:
            raise ValueError(f"No price data for {ticker}")

        chain = await self._registry.options.get_options_chain(ticker)
        vol = await self._registry.volatility.get_volatility_metrics(ticker)

        return self._strategy.build_trade_structure(ticker, earnings, price, vol, chain)

    async def build_custom(
        self,
        ticker: str,
        lower_strike: float | None = None,
        upper_strike: float | None = None,
        short_expiry: date | None = None,
        long_expiry: date | None = None,
    ) -> ConstructedTrade:
        earnings = await self._registry.earnings.get_earnings_date(ticker)
        if earnings is None:
            raise ValueError(f"No earnings date for {ticker}")

        price = await self._registry.price.get_current_price(ticker)
        if price is None:
            raise ValueError(f"No price data for {ticker}")

        chain = await self._registry.options.get_options_chain(ticker)
        vol = await self._registry.volatility.get_volatility_metrics(ticker)

        return self._strategy.build_trade_structure(
            ticker, earnings, price, vol, chain,
            override_lower=lower_strike,
            override_upper=upper_strike,
            override_short_exp=short_expiry,
            override_long_exp=long_expiry,
        )
