from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.core.config import Settings
from app.providers.base import (
    EarningsRecord,
    OptionsChainSnapshot,
    PriceRecord,
    VolatilitySnapshot,
)
from app.services.liquidity import LiquidityCheckResult
from app.services.scoring import ScoringResult

# We will import ConstructedTrade from trade_builder to avoid circular imports for now,
# or we can move the dataclass out. For now, import from trade_builder.
from app.services.trade_builder import ConstructedTrade


class BaseOptionsStrategy(ABC):
    """
    Abstract base class for all options strategies in the ECE engine.
    Enforces a standard contract for scoring, trade construction, and liquidity validation.
    """

    def __init__(self, settings: Settings, registry) -> None:
        self._settings = settings
        self._registry = registry

    @property
    @abstractmethod
    def strategy_type(self) -> str:
        """Returns the unique identifier for the strategy (e.g., 'DOUBLE_CALENDAR')."""
        pass

    @abstractmethod
    def validate_liquidity(
        self,
        price: PriceRecord,
        chain: OptionsChainSnapshot,
        short_exp: date,
        long_exp: date,
    ) -> LiquidityCheckResult:
        """Evaluates if the underlying and options chain have sufficient liquidity."""
        pass

    @abstractmethod
    def calculate_score(
        self,
        ticker: str,
        earnings: EarningsRecord | None,
        price: PriceRecord,
        vol: VolatilitySnapshot,
        chain: OptionsChainSnapshot,
        liquidity: LiquidityCheckResult,
    ) -> ScoringResult:
        """Calculates a 0-100 composite score and recommendation classification."""
        pass

    @abstractmethod
    def build_trade_structure(
        self,
        ticker: str,
        earnings: EarningsRecord,
        price: PriceRecord,
        vol: VolatilitySnapshot,
        chain: OptionsChainSnapshot,
        override_lower: float | None = None,
        override_upper: float | None = None,
        override_short_exp: date | None = None,
        override_long_exp: date | None = None,
    ) -> ConstructedTrade:
        """Builds the actual 4-leg trade structure and calculates pricing."""
        pass


class StrategyFactory:
    """
    Factory for instantiating enabled options strategies.
    """

    def __init__(self, settings: Settings, registry) -> None:
        self._settings = settings
        self._registry = registry

    def get_strategy(self, strategy_id: str) -> BaseOptionsStrategy:
        from app.services.strategies.butterfly import ButterflyStrategy
        from app.services.strategies.double_calendar import DoubleCalendarStrategy

        strategies = {
            "DOUBLE_CALENDAR": DoubleCalendarStrategy(self._settings, self._registry),
            "IRON_BUTTERFLY_ATM": ButterflyStrategy(
                self._settings, self._registry, offset=0.0, strategy_id="IRON_BUTTERFLY_ATM"
            ),
            "IRON_BUTTERFLY_BULLISH": ButterflyStrategy(
                self._settings, self._registry, offset=0.05, strategy_id="IRON_BUTTERFLY_BULLISH"
            ),
        }
        if strategy_id not in strategies:
            raise ValueError(f"Unknown strategy ID: {strategy_id}")
        return strategies[strategy_id]

    def get_active_strategies(self) -> list[BaseOptionsStrategy]:
        """Return all currently active strategy instances."""
        return [
            self.get_strategy("DOUBLE_CALENDAR"),
            self.get_strategy("IRON_BUTTERFLY_ATM"),
        ]
