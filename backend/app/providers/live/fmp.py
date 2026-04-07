from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import FMPSettings
from app.core.logging import get_logger
from app.providers.base import (
    EarningsCalendarProvider,
    EarningsRecord,
    PriceProvider,
    PriceRecord,
    ProviderMeta,
)
from app.providers.live.rate_limiter import AsyncRateLimiter

logger = get_logger(__name__)

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


class FMPEarningsProvider(EarningsCalendarProvider):
    """Earnings calendar data from Financial Modeling Prep API."""

    def __init__(self, settings: FMPSettings) -> None:
        self._api_key = settings.FMP_API_KEY
        self._timeout = settings.FMP_TIMEOUT
        self._max_retries = settings.FMP_MAX_RETRIES
        self._source = "fmp_earnings"
        self._client: httpx.AsyncClient | None = None
        self._limiter = AsyncRateLimiter(settings.FMP_RATE_LIMIT, "fmp_earnings")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=FMP_BASE_URL,
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        await self._limiter.acquire()
        client = await self._get_client()
        p = params or {}
        p["apikey"] = self._api_key
        for attempt in range(self._max_retries):
            try:
                resp = await client.get(path, params=p)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                logger.warning(
                    "fmp_request_retry",
                    path=path,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt == self._max_retries - 1:
                    raise
        return None

    async def get_upcoming_earnings(
        self, tickers: list[str], days_ahead: int = 30
    ) -> list[EarningsRecord]:
        today = date.today()
        end = today + timedelta(days=days_ahead)
        try:
            data = await self._request(
                "/earnings-calendar",
                {"from": today.isoformat(), "to": end.isoformat()},
            )
        except Exception as e:
            logger.error("fmp_earnings_fetch_failed", error=str(e))
            return []

        if not isinstance(data, list):
            return []

        ticker_set = {t.upper() for t in tickers}
        results: list[EarningsRecord] = []
        for item in data:
            sym = (item.get("symbol") or "").upper()
            if sym not in ticker_set:
                continue
            rec = self._parse_earnings(item)
            if rec:
                results.append(rec)

        return sorted(results, key=lambda r: r.earnings_date)

    async def get_earnings_date(self, ticker: str) -> EarningsRecord | None:
        ticker_upper = ticker.upper()
        today = date.today()

        # Query in 2-week windows to stay under the 4000-result API cap
        for week_offset in range(0, 60, 14):
            window_start = today + timedelta(days=week_offset)
            window_end = today + timedelta(days=week_offset + 14)
            try:
                data = await self._request(
                    "/earnings-calendar",
                    {"from": window_start.isoformat(), "to": window_end.isoformat()},
                )
            except Exception as e:
                logger.error("fmp_earnings_date_failed", ticker=ticker, window=week_offset, error=str(e))
                continue

            if not isinstance(data, list):
                continue

            for item in data:
                if (item.get("symbol") or "").upper() == ticker_upper:
                    return self._parse_earnings(item)

        return None

    def _parse_earnings(self, item: dict[str, Any]) -> EarningsRecord | None:
        try:
            sym = item["symbol"]
            earnings_date = date.fromisoformat(item["date"])
        except (KeyError, ValueError):
            return None

        timing = "UNKNOWN"
        raw_time = (item.get("time") or item.get("when") or "").lower()
        if raw_time in ("bmo", "before market open", "pre market"):
            timing = "BEFORE_OPEN"
        elif raw_time in ("amc", "after market close", "post market"):
            timing = "AFTER_CLOSE"

        fiscal_q = item.get("fiscalDateEnding") or item.get("fiscalQuarterEnding")
        quarter = None
        year = None
        if fiscal_q:
            try:
                fd = date.fromisoformat(fiscal_q)
                quarter = f"Q{(fd.month - 1) // 3 + 1}"
                year = fd.year
            except ValueError:
                pass

        return EarningsRecord(
            ticker=sym.upper(),
            earnings_date=earnings_date,
            report_timing=timing,
            confidence="CONFIRMED" if item.get("date") else "ESTIMATED",
            fiscal_quarter=quarter,
            fiscal_year=year,
            meta=ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(timezone.utc),
                confidence_score=0.85,
            ),
        )

    async def health_check(self) -> ProviderMeta:
        try:
            data = await self._request(
                "/earnings-calendar",
                {
                    "from": date.today().isoformat(),
                    "to": (date.today() + timedelta(days=7)).isoformat(),
                },
            )
            ok = isinstance(data, list)
            return ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(timezone.utc),
                confidence_score=0.9 if ok else 0.0,
                error_details=None if ok else "Invalid response format",
            )
        except Exception as e:
            return ProviderMeta(
                source_name=self._source,
                confidence_score=0.0,
                error_details=str(e),
            )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class FMPPriceProvider(PriceProvider):
    """Price data from Financial Modeling Prep API."""

    def __init__(self, settings: FMPSettings) -> None:
        self._api_key = settings.FMP_API_KEY
        self._timeout = settings.FMP_TIMEOUT
        self._max_retries = settings.FMP_MAX_RETRIES
        self._source = "fmp_price"
        self._client: httpx.AsyncClient | None = None
        self._limiter = AsyncRateLimiter(settings.FMP_RATE_LIMIT, "fmp_price")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=FMP_BASE_URL,
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        await self._limiter.acquire()
        client = await self._get_client()
        p = params or {}
        p["apikey"] = self._api_key
        for attempt in range(self._max_retries):
            try:
                resp = await client.get(path, params=p)
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                logger.warning(
                    "fmp_price_retry",
                    path=path,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt == self._max_retries - 1:
                    raise
        return None

    async def get_current_price(self, ticker: str) -> PriceRecord | None:
        try:
            data = await self._request("/quote", {"symbol": ticker.upper()})
        except Exception as e:
            logger.error("fmp_price_failed", ticker=ticker, error=str(e))
            return None

        if not isinstance(data, list) or not data:
            return None

        item = data[0]
        try:
            close = float(item.get("price", item.get("previousClose", 0)))
            return PriceRecord(
                ticker=ticker.upper(),
                trade_date=date.today(),
                open=float(item.get("open", close)),
                high=float(item.get("dayHigh", close)),
                low=float(item.get("dayLow", close)),
                close=close,
                volume=int(item.get("volume", 0)),
                avg_dollar_volume=float(item.get("avgVolume", 0)) * close if item.get("avgVolume") else None,
                meta=ProviderMeta(
                    source_name=self._source,
                    freshness_timestamp=datetime.now(timezone.utc),
                    confidence_score=0.9,
                ),
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error("fmp_price_parse_failed", ticker=ticker, error=str(e))
            return None

    async def get_price_history(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[PriceRecord]:
        try:
            data = await self._request(
                "/historical-price-eod/full",
                {"symbol": ticker.upper(), "from": start_date.isoformat(), "to": end_date.isoformat()},
            )
        except Exception as e:
            logger.error("fmp_history_failed", ticker=ticker, error=str(e))
            return []

        if isinstance(data, dict):
            historical = data.get("historical", [])
        elif isinstance(data, list):
            historical = data
        else:
            return []
        records: list[PriceRecord] = []
        for item in historical:
            try:
                records.append(PriceRecord(
                    ticker=ticker.upper(),
                    trade_date=date.fromisoformat(item["date"]),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=int(item.get("volume", 0)),
                    meta=ProviderMeta(
                        source_name=self._source,
                        freshness_timestamp=datetime.now(timezone.utc),
                        confidence_score=0.9,
                    ),
                ))
            except (KeyError, ValueError):
                continue

        return sorted(records, key=lambda r: r.trade_date)

    async def health_check(self) -> ProviderMeta:
        try:
            data = await self._request("/quote", {"symbol": "AAPL"})
            ok = isinstance(data, list) and len(data) > 0
            return ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(timezone.utc),
                confidence_score=0.9 if ok else 0.0,
                error_details=None if ok else "Invalid response",
            )
        except Exception as e:
            return ProviderMeta(
                source_name=self._source,
                confidence_score=0.0,
                error_details=str(e),
            )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
