from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.providers.base import EarningsCalendarProvider, EarningsRecord, ProviderMeta

MOCK_EARNINGS: dict[str, dict] = {
    "AAPL": {"days_offset": 14, "timing": "AFTER_CLOSE", "confidence": "CONFIRMED", "quarter": "Q2", "year": 2026},
    "MSFT": {"days_offset": 12, "timing": "AFTER_CLOSE", "confidence": "CONFIRMED", "quarter": "Q3", "year": 2026},
    "NVDA": {"days_offset": 18, "timing": "AFTER_CLOSE", "confidence": "CONFIRMED", "quarter": "Q1", "year": 2026},
    "AMZN": {"days_offset": 10, "timing": "AFTER_CLOSE", "confidence": "CONFIRMED", "quarter": "Q1", "year": 2026},
    "META": {"days_offset": 16, "timing": "AFTER_CLOSE", "confidence": "CONFIRMED", "quarter": "Q1", "year": 2026},
    "GOOGL": {"days_offset": 20, "timing": "AFTER_CLOSE", "confidence": "ESTIMATED", "quarter": "Q1", "year": 2026},
    "TSLA": {"days_offset": 8, "timing": "AFTER_CLOSE", "confidence": "CONFIRMED", "quarter": "Q1", "year": 2026},
    "AMD": {"days_offset": 11, "timing": "AFTER_CLOSE", "confidence": "CONFIRMED", "quarter": "Q1", "year": 2026},
    "NFLX": {"days_offset": 9, "timing": "AFTER_CLOSE", "confidence": "CONFIRMED", "quarter": "Q1", "year": 2026},
    "JPM": {"days_offset": 7, "timing": "BEFORE_OPEN", "confidence": "CONFIRMED", "quarter": "Q1", "year": 2026},
    "BAC": {"days_offset": 7, "timing": "BEFORE_OPEN", "confidence": "CONFIRMED", "quarter": "Q1", "year": 2026},
    "XOM": {"days_offset": 25, "timing": "BEFORE_OPEN", "confidence": "ESTIMATED", "quarter": "Q1", "year": 2026},
    "CVX": {"days_offset": 26, "timing": "BEFORE_OPEN", "confidence": "ESTIMATED", "quarter": "Q1", "year": 2026},
    "UNH": {"days_offset": 13, "timing": "BEFORE_OPEN", "confidence": "CONFIRMED", "quarter": "Q1", "year": 2026},
    "COST": {"days_offset": 30, "timing": "AFTER_CLOSE", "confidence": "UNVERIFIED", "quarter": "Q2", "year": 2026},
    "AVGO": {"days_offset": 15, "timing": "AFTER_CLOSE", "confidence": "CONFIRMED", "quarter": "Q2", "year": 2026},
    "PLTR": {"days_offset": 19, "timing": "BEFORE_OPEN", "confidence": "ESTIMATED", "quarter": "Q1", "year": 2026},
    "SPY": {"days_offset": -1, "timing": "UNKNOWN", "confidence": "UNVERIFIED", "quarter": None, "year": None},
    "QQQ": {"days_offset": -1, "timing": "UNKNOWN", "confidence": "UNVERIFIED", "quarter": None, "year": None},
}


class MockEarningsProvider(EarningsCalendarProvider):
    def __init__(self) -> None:
        self._source = "mock_earnings"
        self._last_fetch = datetime.now(UTC)

    async def get_upcoming_earnings(
        self, tickers: list[str], days_ahead: int = 30
    ) -> list[EarningsRecord]:
        today = date.today()
        results: list[EarningsRecord] = []
        for ticker in tickers:
            rec = await self.get_earnings_date(ticker)
            if rec is None:
                continue
            delta = (rec.earnings_date - today).days
            if 0 < delta <= days_ahead:
                results.append(rec)
        return sorted(results, key=lambda r: r.earnings_date)

    async def get_earnings_date(self, ticker: str) -> EarningsRecord | None:
        mock = MOCK_EARNINGS.get(ticker.upper())
        if mock is None or mock["days_offset"] < 0:
            return None
        today = date.today()
        earnings_date = today + timedelta(days=mock["days_offset"])
        return EarningsRecord(
            ticker=ticker.upper(),
            earnings_date=earnings_date,
            report_timing=mock["timing"],
            confidence=mock["confidence"],
            fiscal_quarter=mock["quarter"],
            fiscal_year=mock["year"],
            meta=ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(UTC),
                confidence_score={"CONFIRMED": 0.95, "ESTIMATED": 0.7, "UNVERIFIED": 0.3}.get(
                    mock["confidence"], 0.3
                ),
            ),
        )

    async def health_check(self) -> ProviderMeta:
        return ProviderMeta(
            source_name=self._source,
            freshness_timestamp=datetime.now(UTC),
            confidence_score=1.0,
        )
