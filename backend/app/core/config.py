from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import Environment, OperatingMode, UniverseSource  # noqa: F401

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT.parent / ".env"


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./earnings_engine.db"


class TradierSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    PROVIDER_NAME: str = "tradier"
    TRADIER_ACCESS_TOKEN: str = ""
    TRADIER_BASE_URL: str = "https://api.tradier.com"
    TRADIER_TIMEOUT: int = 30
    TRADIER_MAX_RETRIES: int = 3
    TRADIER_RATE_LIMIT: int = 120

    @property
    def is_configured(self) -> bool:
        return bool(self.TRADIER_ACCESS_TOKEN)


class FMPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    FUNDAMENTALS_PROVIDER: str = "fmp"
    FMP_API_KEY: str = ""
    FMP_TIMEOUT: int = 30
    FMP_MAX_RETRIES: int = 3
    FMP_RATE_LIMIT: int = 300

    @property
    def is_configured(self) -> bool:
        return bool(self.FMP_API_KEY)


class TastyTradeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    OPTIONS_PROVIDER: str = "tastytrade"
    TT_USERNAME: str = ""
    TT_PASSWORD: str = ""
    TT_CLIENT_ID: str = ""
    TT_CLIENT_SECRET: str = ""
    TT_REFRESH_TOKEN: str = ""
    TT_ENV: str = "prod"
    TT_TIMEOUT_SECONDS: int = 30

    @property
    def is_configured(self) -> bool:
        return bool(self.TT_USERNAME and self.TT_PASSWORD)


class FREDSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    FRED_API_KEY: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.FRED_API_KEY)


class ScoringSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCORING_", env_file=str(ENV_FILE), extra="ignore")

    LIQUIDITY_WEIGHT: float = 25.0
    EARNINGS_TIMING_WEIGHT: float = 15.0
    VOL_TERM_STRUCTURE_WEIGHT: float = 20.0
    CONTAINMENT_WEIGHT: float = 15.0
    PRICING_EFFICIENCY_WEIGHT: float = 10.0
    EVENT_CLEANLINESS_WEIGHT: float = 10.0
    HISTORICAL_FIT_WEIGHT: float = 5.0
    IV_HV_GAP_WEIGHT: float = 10.0

    RECOMMEND_THRESHOLD: float = 80.0
    WATCHLIST_THRESHOLD: float = 65.0

    SCORING_VERSION: str = "1.1.0"


class LiquiditySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIQ_", env_file=str(ENV_FILE), extra="ignore")

    MIN_AVG_STOCK_VOLUME: int = 2_000_000
    MIN_AVG_OPTION_VOLUME: int = 50
    MIN_OPEN_INTEREST: int = 100
    MAX_BID_ASK_PCT: float = 0.25
    MAX_BID_ASK_ABS: float = 2.00
    MAX_SPREAD_TO_MID: float = 0.30
    MIN_STRIKE_DENSITY: int = 5
    STRICT_SHORT_DATED_MULTIPLIER: float = 1.5


class EarningsWindowSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EARN_", env_file=str(ENV_FILE), extra="ignore")

    MIN_DAYS_TO_EARNINGS: int = 7
    MAX_DAYS_TO_EARNINGS: int = 21
    EXIT_DAYS_BEFORE_EARNINGS: int = 1
    REQUIRE_CONFIRMED_DATE: bool = True


class SP500PreFilterSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PREFILTER_", env_file=str(ENV_FILE), extra="ignore")

    ENABLED: bool = True
    MIN_STOCK_PRICE: float = 100.0
    MIN_MARKET_CAP_B: float = 10.0
    MIN_AVG_OPTION_VOLUME: int = 1000
    REQUIRE_WEEKLY_OPTIONS: bool = True
    MIN_EXPIRATION_COUNT: int = 6


class DataSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    STRICT_LIVE_DATA: bool = True
    ALLOW_SIMULATION: bool = False
    UNIVERSE_SOURCE: UniverseSource = UniverseSource.STATIC

    @field_validator("UNIVERSE_SOURCE", mode="before")
    @classmethod
    def normalise_universe_source(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.upper()
        return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    ENVIRONMENT: Environment = Environment.LOCAL
    LOG_LEVEL: str = "INFO"
    DISCOUNT_RATE: float = 0.05

    OPERATING_MODE: OperatingMode = OperatingMode.STRICT

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api/v1"

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    db: DatabaseSettings = DatabaseSettings()
    tradier: TradierSettings = TradierSettings()
    fmp: FMPSettings = FMPSettings()
    tastytrade: TastyTradeSettings = TastyTradeSettings()
    fred: FREDSettings = FREDSettings()
    scoring: ScoringSettings = ScoringSettings()
    liquidity: LiquiditySettings = LiquiditySettings()
    earnings_window: EarningsWindowSettings = EarningsWindowSettings()
    data: DataSettings = DataSettings()
    prefilter: SP500PreFilterSettings = SP500PreFilterSettings()

    DEFAULT_UNIVERSE: list[str] = [
        "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL",
        "TSLA", "AMD", "NFLX", "JPM", "BAC", "XOM", "CVX", "UNH",
        "COST", "AVGO", "PLTR",
    ]


def get_settings() -> Settings:
    return Settings()
