from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
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

# Built-in S&P 500 constituent list (Q1 2025).
# Used as fallback when FMP /sp500-constituent is unavailable.
_SP500_TICKERS: list[str] = [
    "MMM",
    "AOS",
    "ABT",
    "ABBV",
    "ACN",
    "ADBE",
    "AMD",
    "AES",
    "AFL",
    "A",
    "APD",
    "ABNB",
    "AKAM",
    "ALB",
    "ARE",
    "ALGN",
    "ALLE",
    "LNT",
    "ALL",
    "GOOGL",
    "GOOG",
    "MO",
    "AMZN",
    "AMCR",
    "AEE",
    "AAL",
    "AEP",
    "AXP",
    "AIG",
    "AMT",
    "AWK",
    "AMP",
    "AME",
    "AMGN",
    "APH",
    "ADI",
    "ANSS",
    "AON",
    "APA",
    "AAPL",
    "AMAT",
    "APTV",
    "ACGL",
    "ADM",
    "ANET",
    "AJG",
    "AIZ",
    "T",
    "ATO",
    "ADSK",
    "AZO",
    "AVB",
    "AVY",
    "AXON",
    "BKR",
    "BALL",
    "BAC",
    "BAX",
    "BDX",
    "BRK.B",
    "BBY",
    "BIO",
    "TECH",
    "BIIB",
    "BLK",
    "BX",
    "BA",
    "BKNG",
    "BWA",
    "BSX",
    "BMY",
    "AVGO",
    "BR",
    "BRO",
    "BF.B",
    "BLDR",
    "BG",
    "CDNS",
    "CZR",
    "CPT",
    "CPB",
    "COF",
    "CAH",
    "KMX",
    "CCL",
    "CARR",
    "CTLT",
    "CAT",
    "CBOE",
    "CBRE",
    "CDW",
    "CE",
    "COR",
    "CNC",
    "CNX",
    "CDAY",
    "CF",
    "CRL",
    "SCHW",
    "CHTR",
    "CVX",
    "CMG",
    "CB",
    "CHD",
    "CI",
    "CINF",
    "CTAS",
    "CSCO",
    "C",
    "CFG",
    "CLX",
    "CME",
    "CMS",
    "KO",
    "CTSH",
    "CL",
    "CMCSA",
    "CMA",
    "CAG",
    "COP",
    "ED",
    "STZ",
    "CEG",
    "COO",
    "CPRT",
    "GLW",
    "CTVA",
    "CSGP",
    "COST",
    "CTRA",
    "CCI",
    "CSX",
    "CMI",
    "CVS",
    "DHI",
    "DHR",
    "DRI",
    "DVA",
    "DAY",
    "DECK",
    "DE",
    "DAL",
    "DVN",
    "DXCM",
    "FANG",
    "DLR",
    "DFS",
    "DG",
    "DLTR",
    "D",
    "DPZ",
    "DOV",
    "DOW",
    "DHI",
    "DTE",
    "DUK",
    "DD",
    "EMN",
    "ETN",
    "EBAY",
    "ECL",
    "EIX",
    "EW",
    "EA",
    "ELV",
    "LLY",
    "EMR",
    "ENPH",
    "ETR",
    "EOG",
    "EPAM",
    "EQT",
    "EFX",
    "EQIX",
    "EQR",
    "ESS",
    "EL",
    "ETSY",
    "EG",
    "EVRG",
    "ES",
    "EXC",
    "EXPE",
    "EXPD",
    "EXR",
    "XOM",
    "FFIV",
    "FDS",
    "FICO",
    "FAST",
    "FRT",
    "FDX",
    "FIS",
    "FITB",
    "FSLR",
    "FE",
    "FI",
    "FMC",
    "F",
    "FTNT",
    "FTV",
    "FOXA",
    "FOX",
    "BEN",
    "FCX",
    "GRMN",
    "IT",
    "GE",
    "GEHC",
    "GEV",
    "GEN",
    "GNRC",
    "GD",
    "GIS",
    "GM",
    "GPC",
    "GILD",
    "GPN",
    "GL",
    "GDDY",
    "GS",
    "HAL",
    "HIG",
    "HAS",
    "HCA",
    "DOC",
    "HSIC",
    "HSY",
    "HES",
    "HPE",
    "HLT",
    "HOLX",
    "HD",
    "HON",
    "HRL",
    "HST",
    "HWM",
    "HPQ",
    "HUBB",
    "HUM",
    "HBAN",
    "HII",
    "IBM",
    "IEX",
    "IDXX",
    "ITW",
    "INCY",
    "IR",
    "PODD",
    "INTC",
    "ICE",
    "IFF",
    "IP",
    "IPG",
    "INTU",
    "ISRG",
    "IVZ",
    "INVH",
    "IQV",
    "IRM",
    "JBHT",
    "JBL",
    "JKHY",
    "J",
    "JNJ",
    "JCI",
    "JPM",
    "JNPR",
    "K",
    "KVUE",
    "KDP",
    "KEY",
    "KEYS",
    "KMB",
    "KIM",
    "KMI",
    "KLAC",
    "KHC",
    "KR",
    "LHX",
    "LH",
    "LRCX",
    "LW",
    "LVS",
    "LDOS",
    "LEN",
    "LIN",
    "LYV",
    "LKQ",
    "LMT",
    "L",
    "LOW",
    "LULU",
    "LYB",
    "MTB",
    "MRO",
    "MPC",
    "MKTX",
    "MAR",
    "MMC",
    "MLM",
    "MAS",
    "MA",
    "MTCH",
    "MKC",
    "MCD",
    "MCK",
    "MDT",
    "MRK",
    "META",
    "MET",
    "MTD",
    "MGM",
    "MCHP",
    "MU",
    "MSFT",
    "MAA",
    "MRNA",
    "MHK",
    "MOH",
    "TAP",
    "MDLZ",
    "MPWR",
    "MNST",
    "MCO",
    "MS",
    "MOS",
    "MSI",
    "MSCI",
    "NDAQ",
    "NTAP",
    "NFLX",
    "NEM",
    "NWSA",
    "NWS",
    "NEE",
    "NKE",
    "NI",
    "NDSN",
    "NSC",
    "NTRS",
    "NOC",
    "NCLH",
    "NRG",
    "NUE",
    "NVDA",
    "NVR",
    "NXPI",
    "ORLY",
    "OXY",
    "ODFL",
    "OMC",
    "ON",
    "OKE",
    "ORCL",
    "OTIS",
    "PCAR",
    "PKG",
    "PANW",
    "PH",
    "PAYX",
    "PAYC",
    "PYPL",
    "PNR",
    "PEP",
    "PFE",
    "PCG",
    "PM",
    "PSX",
    "PNW",
    "PNC",
    "POOL",
    "PPG",
    "PPL",
    "PFG",
    "PG",
    "PGR",
    "PLD",
    "PRU",
    "PEG",
    "PTC",
    "PSA",
    "PHM",
    "QRVO",
    "PWR",
    "QCOM",
    "DGX",
    "RL",
    "RJF",
    "RTX",
    "O",
    "REG",
    "REGN",
    "RF",
    "RSG",
    "RMD",
    "RVTY",
    "ROK",
    "ROL",
    "ROP",
    "ROST",
    "RCL",
    "SPGI",
    "CRM",
    "SBAC",
    "SLB",
    "STX",
    "SRE",
    "NOW",
    "SHW",
    "SPG",
    "SWKS",
    "SJM",
    "SW",
    "SNA",
    "SOLV",
    "SO",
    "LUV",
    "SWK",
    "SBUX",
    "STT",
    "STLD",
    "STE",
    "SYK",
    "SMCI",
    "SYF",
    "SNPS",
    "SYY",
    "TMUS",
    "TROW",
    "TTWO",
    "TPR",
    "TRGP",
    "TGT",
    "TEL",
    "TDY",
    "TFX",
    "TER",
    "TSLA",
    "TXN",
    "TXT",
    "TMO",
    "TJX",
    "TSCO",
    "TT",
    "TDG",
    "TRV",
    "TRMB",
    "TFC",
    "TYL",
    "TSN",
    "USB",
    "UBER",
    "UDR",
    "ULTA",
    "UNP",
    "UAL",
    "UPS",
    "URI",
    "UNH",
    "UHS",
    "VLO",
    "VTR",
    "VLTO",
    "VRSN",
    "VRSK",
    "VZ",
    "VRTX",
    "VTRS",
    "VICI",
    "V",
    "VST",
    "VMC",
    "WRB",
    "GWW",
    "WAB",
    "WBA",
    "WMT",
    "DIS",
    "WBD",
    "WM",
    "WAT",
    "WEC",
    "WFC",
    "WELL",
    "WST",
    "WDC",
    "WY",
    "WMB",
    "WTW",
    "WYNN",
    "XEL",
    "XYL",
    "YUM",
    "ZBRA",
    "ZBH",
    "ZTS",
]


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
                logger.error(
                    "fmp_earnings_date_failed", ticker=ticker, window=week_offset, error=str(e)
                )
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
            confidence=self._infer_confidence(item, earnings_date),
            fiscal_quarter=quarter,
            fiscal_year=year,
            meta=ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(UTC),
                confidence_score=0.85,
            ),
        )

    @staticmethod
    def _infer_confidence(item: dict[str, Any], earnings_date: date) -> str:
        """Infer earnings date confidence from FMP response fields.

        FMP does not provide an explicit confidence flag. We use heuristics:
        - Dates with EPS estimates or revenue data are typically confirmed.
        - Dates with known timing (BMO/AMC) are more reliable.
        - Dates >45 days out without supporting data are likely estimates.
        """
        has_eps = item.get("epsEstimated") is not None or item.get("eps") is not None
        has_revenue = item.get("revenueEstimated") is not None or item.get("revenue") is not None
        has_timing = (item.get("time") or item.get("when") or "").lower() in (
            "bmo", "before market open", "pre market",
            "amc", "after market close", "post market",
        )
        days_out = (earnings_date - date.today()).days

        if has_eps or has_revenue:
            return "CONFIRMED"
        if has_timing and days_out <= 30:
            return "CONFIRMED"
        if days_out > 45:
            return "ESTIMATED"
        return "ESTIMATED"

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
                freshness_timestamp=datetime.now(UTC),
                confidence_score=0.9 if ok else 0.0,
                error_details=None if ok else "Invalid response format",
            )
        except Exception as e:
            return ProviderMeta(
                source_name=self._source,
                confidence_score=0.0,
                error_details=str(e),
            )

    async def get_sp500_tickers(self) -> list[str]:
        """Return S&P 500 constituent tickers.
        Tries FMP /sp500-constituent first; falls back to the built-in static list
        (updated Q1 2025) if the endpoint is unavailable or behind a higher tier."""
        try:
            data = await self._request("/sp500-constituent")
            if isinstance(data, list) and len(data) > 100:
                tickers = [
                    item["symbol"] for item in data if isinstance(item, dict) and item.get("symbol")
                ]
                logger.info("sp500_tickers_from_fmp", count=len(tickers))
                return tickers
        except Exception as e:
            logger.warning("fmp_sp500_endpoint_unavailable", error=str(e))

        logger.info("sp500_tickers_from_builtin_list")
        return _SP500_TICKERS

    async def get_tickers_with_earnings_in_window(
        self, tickers: list[str], min_days: int, max_days: int
    ) -> list[str]:
        """Bulk-fetch earnings calendar for the window.

        Returns only tickers that have earnings.
        """
        today = date.today()
        window_start = today + timedelta(days=min_days)
        window_end = today + timedelta(days=max_days)
        ticker_set = {t.upper() for t in tickers}
        matched: set[str] = set()

        # Query in 14-day windows to stay under API cap
        current = window_start
        while current <= window_end:
            chunk_end = min(current + timedelta(days=14), window_end)
            try:
                data = await self._request(
                    "/earnings-calendar",
                    {"from": current.isoformat(), "to": chunk_end.isoformat()},
                )
                if isinstance(data, list):
                    for item in data:
                        sym = (item.get("symbol") or "").upper()
                        if sym in ticker_set:
                            matched.add(sym)
            except Exception as e:
                logger.warning(
                    "fmp_earnings_window_chunk_failed", window=current.isoformat(), error=str(e)
                )
            current = chunk_end + timedelta(days=1)

        logger.info(
            "sp500_earnings_prefilter", total_sp500=len(tickers), with_earnings=len(matched)
        )
        return sorted(matched)

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
                avg_dollar_volume=float(item.get("avgVolume", 0)) * close
                if item.get("avgVolume")
                else None,
                meta=ProviderMeta(
                    source_name=self._source,
                    freshness_timestamp=datetime.now(UTC),
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
                {
                    "symbol": ticker.upper(),
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                },
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
                records.append(
                    PriceRecord(
                        ticker=ticker.upper(),
                        trade_date=date.fromisoformat(item["date"]),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=int(item.get("volume", 0)),
                        meta=ProviderMeta(
                            source_name=self._source,
                            freshness_timestamp=datetime.now(UTC),
                            confidence_score=0.9,
                        ),
                    )
                )
            except (KeyError, ValueError):
                continue

        return sorted(records, key=lambda r: r.trade_date)

    async def get_bulk_quotes(self, tickers: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch price + market-cap data for multiple tickers concurrently.
        Returns dict keyed by uppercase ticker symbol."""
        import asyncio

        async def _fetch_one(ticker: str) -> tuple[str, dict[str, Any] | None]:
            try:
                data = await self._request("/quote", {"symbol": ticker.upper()})
                if isinstance(data, list) and data:
                    return ticker.upper(), data[0]
            except Exception as e:
                logger.warning("fmp_quote_single_failed", ticker=ticker, error=str(e))
            return ticker.upper(), None

        concurrency = 10
        results: dict[str, dict[str, Any]] = {}
        for i in range(0, len(tickers), concurrency):
            batch = tickers[i : i + concurrency]
            pairs = await asyncio.gather(*[_fetch_one(t) for t in batch])
            for sym, item in pairs:
                if item:
                    results[sym] = item
        return results

    async def health_check(self) -> ProviderMeta:
        try:
            data = await self._request("/quote", {"symbol": "AAPL"})
            ok = isinstance(data, list) and len(data) > 0
            return ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(UTC),
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
