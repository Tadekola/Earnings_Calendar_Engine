from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from app.providers.base import PriceProvider, PriceRecord, ProviderMeta

MOCK_PRICES: dict[str, dict] = {
    "SPY": {"price": 525.0, "vol": 0.12, "avg_vol": 80_000_000},
    "QQQ": {"price": 445.0, "vol": 0.15, "avg_vol": 50_000_000},
    "AAPL": {"price": 195.0, "vol": 0.18, "avg_vol": 55_000_000},
    "MSFT": {"price": 420.0, "vol": 0.16, "avg_vol": 22_000_000},
    "NVDA": {"price": 880.0, "vol": 0.30, "avg_vol": 45_000_000},
    "AMZN": {"price": 185.0, "vol": 0.22, "avg_vol": 35_000_000},
    "META": {"price": 510.0, "vol": 0.25, "avg_vol": 18_000_000},
    "GOOGL": {"price": 165.0, "vol": 0.20, "avg_vol": 25_000_000},
    "TSLA": {"price": 175.0, "vol": 0.45, "avg_vol": 90_000_000},
    "AMD": {"price": 160.0, "vol": 0.35, "avg_vol": 40_000_000},
    "NFLX": {"price": 625.0, "vol": 0.28, "avg_vol": 8_000_000},
    "JPM": {"price": 200.0, "vol": 0.15, "avg_vol": 10_000_000},
    "BAC": {"price": 38.0, "vol": 0.18, "avg_vol": 35_000_000},
    "XOM": {"price": 115.0, "vol": 0.14, "avg_vol": 15_000_000},
    "CVX": {"price": 160.0, "vol": 0.14, "avg_vol": 8_000_000},
    "UNH": {"price": 520.0, "vol": 0.16, "avg_vol": 3_500_000},
    "COST": {"price": 740.0, "vol": 0.14, "avg_vol": 2_500_000},
    "AVGO": {"price": 1350.0, "vol": 0.25, "avg_vol": 3_000_000},
    "PLTR": {"price": 24.0, "vol": 0.50, "avg_vol": 60_000_000},
}


class MockPriceProvider(PriceProvider):
    def __init__(self, seed: int = 42) -> None:
        self._source = "mock_market"
        self._rng = random.Random(seed)

    async def get_current_price(self, ticker: str) -> PriceRecord | None:
        mock = MOCK_PRICES.get(ticker.upper())
        if mock is None:
            return None
        price = mock["price"]
        daily_move = price * mock["vol"] / 16  # approx daily vol
        close = price + self._rng.uniform(-daily_move, daily_move)
        high = close + abs(self._rng.gauss(0, daily_move * 0.5))
        low = close - abs(self._rng.gauss(0, daily_move * 0.5))
        open_price = close + self._rng.uniform(-daily_move * 0.3, daily_move * 0.3)
        return PriceRecord(
            ticker=ticker.upper(),
            trade_date=date.today(),
            open=round(open_price, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close, 2),
            volume=int(mock["avg_vol"] * self._rng.uniform(0.7, 1.3)),
            avg_dollar_volume=round(close * mock["avg_vol"], 2),
            meta=ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(timezone.utc),
                confidence_score=0.95,
            ),
        )

    async def get_price_history(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[PriceRecord]:
        mock = MOCK_PRICES.get(ticker.upper())
        if mock is None:
            return []
        records: list[PriceRecord] = []
        price = mock["price"]
        daily_vol = mock["vol"] / 16
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                ret = self._rng.gauss(0, daily_vol)
                price = price * (1 + ret)
                high = price * (1 + abs(self._rng.gauss(0, daily_vol * 0.5)))
                low = price * (1 - abs(self._rng.gauss(0, daily_vol * 0.5)))
                open_p = price * (1 + self._rng.uniform(-daily_vol * 0.3, daily_vol * 0.3))
                records.append(
                    PriceRecord(
                        ticker=ticker.upper(),
                        trade_date=current,
                        open=round(open_p, 2),
                        high=round(high, 2),
                        low=round(low, 2),
                        close=round(price, 2),
                        volume=int(mock["avg_vol"] * self._rng.uniform(0.6, 1.4)),
                        meta=ProviderMeta(
                            source_name=self._source,
                            freshness_timestamp=datetime.now(timezone.utc),
                            confidence_score=0.9,
                        ),
                    )
                )
            current += timedelta(days=1)
        return records

    async def health_check(self) -> ProviderMeta:
        return ProviderMeta(
            source_name=self._source,
            freshness_timestamp=datetime.now(timezone.utc),
            confidence_score=1.0,
        )
