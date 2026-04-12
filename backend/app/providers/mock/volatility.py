from __future__ import annotations

import random
from datetime import UTC, date, datetime

from app.providers.base import ProviderMeta, VolatilityMetricsProvider, VolatilitySnapshot

MOCK_VOL_DATA: dict[str, dict] = {
    "SPY": {
        "rv10": 0.11,
        "rv20": 0.12,
        "rv30": 0.13,
        "atr": 5.2,
        "ivr": 35,
        "ivp": 30,
        "front": 0.15,
        "back": 0.14,
    },
    "QQQ": {
        "rv10": 0.14,
        "rv20": 0.15,
        "rv30": 0.16,
        "atr": 6.5,
        "ivr": 40,
        "ivp": 35,
        "front": 0.18,
        "back": 0.16,
    },
    "AAPL": {
        "rv10": 0.17,
        "rv20": 0.18,
        "rv30": 0.19,
        "atr": 3.8,
        "ivr": 45,
        "ivp": 42,
        "front": 0.28,
        "back": 0.22,
    },
    "MSFT": {
        "rv10": 0.15,
        "rv20": 0.16,
        "rv30": 0.17,
        "atr": 7.0,
        "ivr": 38,
        "ivp": 33,
        "front": 0.24,
        "back": 0.20,
    },
    "NVDA": {
        "rv10": 0.32,
        "rv20": 0.30,
        "rv30": 0.28,
        "atr": 28.0,
        "ivr": 55,
        "ivp": 50,
        "front": 0.48,
        "back": 0.36,
    },
    "AMZN": {
        "rv10": 0.22,
        "rv20": 0.23,
        "rv30": 0.24,
        "atr": 4.5,
        "ivr": 42,
        "ivp": 38,
        "front": 0.33,
        "back": 0.27,
    },
    "META": {
        "rv10": 0.25,
        "rv20": 0.26,
        "rv30": 0.27,
        "atr": 13.0,
        "ivr": 50,
        "ivp": 45,
        "front": 0.38,
        "back": 0.30,
    },
    "GOOGL": {
        "rv10": 0.19,
        "rv20": 0.20,
        "rv30": 0.21,
        "atr": 3.5,
        "ivr": 36,
        "ivp": 32,
        "front": 0.28,
        "back": 0.24,
    },
    "TSLA": {
        "rv10": 0.48,
        "rv20": 0.45,
        "rv30": 0.42,
        "atr": 8.5,
        "ivr": 62,
        "ivp": 58,
        "front": 0.65,
        "back": 0.50,
    },
    "AMD": {
        "rv10": 0.38,
        "rv20": 0.35,
        "rv30": 0.33,
        "atr": 6.0,
        "ivr": 52,
        "ivp": 48,
        "front": 0.50,
        "back": 0.40,
    },
    "NFLX": {
        "rv10": 0.28,
        "rv20": 0.27,
        "rv30": 0.26,
        "atr": 18.0,
        "ivr": 48,
        "ivp": 44,
        "front": 0.42,
        "back": 0.33,
    },
    "JPM": {
        "rv10": 0.14,
        "rv20": 0.15,
        "rv30": 0.16,
        "atr": 3.2,
        "ivr": 30,
        "ivp": 25,
        "front": 0.22,
        "back": 0.19,
    },
    "BAC": {
        "rv10": 0.16,
        "rv20": 0.17,
        "rv30": 0.18,
        "atr": 0.7,
        "ivr": 32,
        "ivp": 28,
        "front": 0.24,
        "back": 0.21,
    },
    "XOM": {
        "rv10": 0.13,
        "rv20": 0.14,
        "rv30": 0.15,
        "atr": 1.8,
        "ivr": 28,
        "ivp": 22,
        "front": 0.19,
        "back": 0.17,
    },
    "CVX": {
        "rv10": 0.13,
        "rv20": 0.14,
        "rv30": 0.15,
        "atr": 2.5,
        "ivr": 26,
        "ivp": 20,
        "front": 0.19,
        "back": 0.17,
    },
    "UNH": {
        "rv10": 0.15,
        "rv20": 0.16,
        "rv30": 0.17,
        "atr": 9.0,
        "ivr": 34,
        "ivp": 30,
        "front": 0.24,
        "back": 0.20,
    },
    "COST": {
        "rv10": 0.13,
        "rv20": 0.14,
        "rv30": 0.15,
        "atr": 11.0,
        "ivr": 25,
        "ivp": 20,
        "front": 0.20,
        "back": 0.17,
    },
    "AVGO": {
        "rv10": 0.24,
        "rv20": 0.25,
        "rv30": 0.26,
        "atr": 35.0,
        "ivr": 46,
        "ivp": 42,
        "front": 0.36,
        "back": 0.29,
    },
    "PLTR": {
        "rv10": 0.52,
        "rv20": 0.50,
        "rv30": 0.48,
        "atr": 1.3,
        "ivr": 65,
        "ivp": 60,
        "front": 0.72,
        "back": 0.55,
    },
}


class MockVolatilityProvider(VolatilityMetricsProvider):
    def __init__(self, seed: int = 42) -> None:
        self._source = "mock_volatility"
        self._rng = random.Random(seed)

    async def get_volatility_metrics(self, ticker: str) -> VolatilitySnapshot:
        data = MOCK_VOL_DATA.get(ticker.upper())
        if data is None:
            return VolatilitySnapshot(
                ticker=ticker.upper(),
                as_of_date=date.today(),
                meta=ProviderMeta(
                    source_name=self._source,
                    freshness_timestamp=datetime.now(UTC),
                    confidence_score=0.0,
                    error_details=f"No mock volatility data for {ticker}",
                ),
            )
        def jitter(v: float) -> float:
            return round(v * self._rng.uniform(0.95, 1.05), 4)
        front_iv = jitter(data["front"])
        back_iv = jitter(data["back"])
        slope = (
            round((back_iv - front_iv) / back_iv, 4) if back_iv > 0 else 0.0
        )
        return VolatilitySnapshot(
            ticker=ticker.upper(),
            as_of_date=date.today(),
            realized_vol_10d=jitter(data["rv10"]),
            realized_vol_20d=jitter(data["rv20"]),
            realized_vol_30d=jitter(data["rv30"]),
            atr_14d=round(data["atr"] * self._rng.uniform(0.9, 1.1), 2),
            iv_rank=round((data["ivr"] + self._rng.uniform(-3, 3)) / 100, 4),
            iv_percentile=round((data["ivp"] + self._rng.uniform(-3, 3)) / 100, 4),
            front_expiry_iv=front_iv,
            back_expiry_iv=back_iv,
            term_structure_slope=slope,
            meta=ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(UTC),
                confidence_score=0.9,
            ),
        )

    async def health_check(self) -> ProviderMeta:
        return ProviderMeta(
            source_name=self._source,
            freshness_timestamp=datetime.now(UTC),
            confidence_score=1.0,
        )
