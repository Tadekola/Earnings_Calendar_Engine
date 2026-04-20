from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.config import Settings
from app.core.enums import LegSide, OptionType, RecommendationClass
from app.core.logging import get_logger
from app.core.security import RISK_DISCLAIMER
from app.providers.base import (
    OptionRecord,
)
from app.providers.registry import ProviderRegistry
from app.services._price_fallback import get_tradier_fallback_price

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
    layer_id: str | None = None
    account_id: str | None = None


class TradeConstructionEngine:
    """
    Facade that delegates trade building to the active strategy based on the Phase State Machine.
    """

    def __init__(
        self, settings: Settings, registry: ProviderRegistry, force_strategy: Any | None = None
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._force_strategy = force_strategy

        from app.services.base_strategy import StrategyFactory

        self._strategy_factory = StrategyFactory(settings, registry)

    def _determine_phase(self, ticker: str, days_to: int) -> tuple[str, str, str]:
        if ticker.upper() == "XSP":
            return "XSP_IRON_BUTTERFLY", "L4", "IBKR_PERSONAL"
        elif days_to >= 7:
            return "DOUBLE_CALENDAR", "L1", "SHENIDO"
        elif 0 <= days_to <= 2:
            return "IRON_BUTTERFLY_ATM", "L2", "SHENIDO"
        elif -3 <= days_to < 0:
            return "IRON_BUTTERFLY_BULLISH", "L3", "SHENIDO"
        return "DOUBLE_CALENDAR", "UNKNOWN", "SHENIDO"

    async def build_recommended(self, ticker: str) -> ConstructedTrade:
        earnings = await self._registry.earnings.get_earnings_date(ticker)
        if earnings is None and ticker.upper() != "XSP":
            raise ValueError(f"No earnings date for {ticker}")

        days_to = (earnings.earnings_date - date.today()).days if earnings else 0
        strategy_id, layer_id, account_id = self._determine_phase(ticker, days_to)
        if self._force_strategy:
            strategy = self._force_strategy
        else:
            strategy = self._strategy_factory.get_strategy(strategy_id)

        price = await self._registry.price.get_current_price(ticker)
        if price is None:
            price = await get_tradier_fallback_price(self._registry, ticker)
        if price is None:
            raise ValueError(f"No price data for {ticker}")

        chain = await self._registry.options.get_options_chain(ticker)
        vol = await self._registry.volatility.get_volatility_metrics(ticker)

        trade = strategy.build_trade_structure(ticker, earnings, price, vol, chain)
        trade.layer_id = layer_id
        trade.account_id = account_id
        return trade

    async def build_custom(
        self,
        ticker: str,
        lower_strike: float | None = None,
        upper_strike: float | None = None,
        short_expiry: date | None = None,
        long_expiry: date | None = None,
    ) -> ConstructedTrade:
        earnings = await self._registry.earnings.get_earnings_date(ticker)
        if earnings is None and ticker.upper() != "XSP":
            raise ValueError(f"No earnings date for {ticker}")

        days_to = (earnings.earnings_date - date.today()).days if earnings else 0
        strategy_id, layer_id, account_id = self._determine_phase(ticker, days_to)
        if self._force_strategy:
            strategy = self._force_strategy
        else:
            strategy = self._strategy_factory.get_strategy(strategy_id)

        price = await self._registry.price.get_current_price(ticker)
        if price is None:
            price = await get_tradier_fallback_price(self._registry, ticker)
        if price is None:
            raise ValueError(f"No price data for {ticker}")

        chain = await self._registry.options.get_options_chain(ticker)
        vol = await self._registry.volatility.get_volatility_metrics(ticker)

        trade = strategy.build_trade_structure(
            ticker,
            earnings,
            price,
            vol,
            chain,
            override_lower=lower_strike,
            override_upper=upper_strike,
            override_short_exp=short_expiry,
            override_long_exp=long_expiry,
        )
        trade.layer_id = layer_id
        trade.account_id = account_id
        return trade
