from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger
from app.providers.base import (
    EarningsCalendarProvider,
    OptionsChainProvider,
    PriceProvider,
    ProviderMeta,
    VolatilityMetricsProvider,
)
from app.providers.mock.earnings import MockEarningsProvider
from app.providers.mock.market_data import MockPriceProvider
from app.providers.mock.options import MockOptionsProvider
from app.providers.mock.volatility import MockVolatilityProvider

logger = get_logger(__name__)


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._earnings: EarningsCalendarProvider | None = None
        self._price: PriceProvider | None = None
        self._options: OptionsChainProvider | None = None
        self._volatility: VolatilityMetricsProvider | None = None

    def initialize(self) -> None:
        use_live = self._settings.data.STRICT_LIVE_DATA and not self._settings.data.ALLOW_SIMULATION

        # Earnings provider
        if use_live and self._settings.fmp.is_configured:
            from app.providers.live.fmp import FMPEarningsProvider

            logger.info("provider_init", provider="earnings", type="fmp_live")
            self._earnings = FMPEarningsProvider(self._settings.fmp)
        else:
            logger.info("provider_init", provider="earnings", type="mock")
            self._earnings = MockEarningsProvider()

        # Price provider
        if use_live and self._settings.fmp.is_configured:
            from app.providers.live.fmp import FMPPriceProvider

            logger.info("provider_init", provider="price", type="fmp_live")
            self._price = FMPPriceProvider(self._settings.fmp)
        else:
            logger.info("provider_init", provider="price", type="mock")
            self._price = MockPriceProvider()

        # Options provider
        if use_live and self._settings.tradier.is_configured:
            from app.providers.live.tradier import TradierOptionsProvider

            logger.info("provider_init", provider="options", type="tradier_live")
            self._options = TradierOptionsProvider(self._settings.tradier)
        else:
            logger.info("provider_init", provider="options", type="mock")
            self._options = MockOptionsProvider()

        # Volatility provider — TT primary (authoritative IVR/IVP/HV),
        # ComputedVolatilityProvider as fallback for ATR and short-window RV
        if use_live and (self._settings.fmp.is_configured or self._settings.tradier.is_configured):
            from app.providers.live.volatility import ComputedVolatilityProvider

            computed = ComputedVolatilityProvider(self._price, self._options)
            if use_live and self._settings.tastytrade.is_configured:
                from app.providers.live.tastytrade import (
                    TastyTradeClient,
                    TastyTradeVolatilityProvider,
                )

                tt_client = TastyTradeClient(self._settings.tastytrade)
                logger.info(
                    "provider_init",
                    provider="volatility",
                    type="tastytrade_live",
                    fallback="computed_live",
                )
                self._volatility = TastyTradeVolatilityProvider(
                    client=tt_client, fallback=computed
                )
            else:
                logger.info("provider_init", provider="volatility", type="computed_live")
                self._volatility = computed
        else:
            logger.info("provider_init", provider="volatility", type="mock")
            self._volatility = MockVolatilityProvider()

    @property
    def earnings(self) -> EarningsCalendarProvider:
        if self._earnings is None:
            raise ConfigurationError("Earnings provider not initialized")
        return self._earnings

    @property
    def price(self) -> PriceProvider:
        if self._price is None:
            raise ConfigurationError("Price provider not initialized")
        return self._price

    @property
    def options(self) -> OptionsChainProvider:
        if self._options is None:
            raise ConfigurationError("Options provider not initialized")
        return self._options

    @property
    def volatility(self) -> VolatilityMetricsProvider:
        if self._volatility is None:
            raise ConfigurationError("Volatility provider not initialized")
        return self._volatility

    async def health_check_all(self) -> dict[str, ProviderMeta]:
        results: dict[str, ProviderMeta] = {}
        for name, provider in [
            ("earnings", self._earnings),
            ("price", self._price),
            ("options", self._options),
            ("volatility", self._volatility),
        ]:
            if provider is not None:
                try:
                    results[name] = await provider.health_check()
                except Exception as e:
                    results[name] = ProviderMeta(
                        source_name=name,
                        confidence_score=0.0,
                        error_details=str(e),
                    )
            else:
                results[name] = ProviderMeta(
                    source_name=name,
                    confidence_score=0.0,
                    error_details="Not configured",
                )
        return results
