from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.core.config import TradierSettings
from app.core.logging import get_logger
from app.providers.base import (
    OptionRecord,
    OptionsChainProvider,
    OptionsChainSnapshot,
    ProviderMeta,
)
from app.providers.live.rate_limiter import AsyncRateLimiter

logger = get_logger(__name__)


class TradierOptionsProvider(OptionsChainProvider):
    """Options chain data from Tradier API."""

    def __init__(self, settings: TradierSettings) -> None:
        self._token = settings.TRADIER_ACCESS_TOKEN
        self._base_url = settings.TRADIER_BASE_URL
        self._timeout = settings.TRADIER_TIMEOUT
        self._max_retries = settings.TRADIER_MAX_RETRIES
        self._source = "tradier_options"
        self._client: httpx.AsyncClient | None = None
        self._limiter = AsyncRateLimiter(settings.TRADIER_RATE_LIMIT, "tradier")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                },
            )
        return self._client

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        await self._limiter.acquire()
        client = await self._get_client()
        for attempt in range(self._max_retries):
            try:
                resp = await client.get(path, params=params or {})
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                logger.warning(
                    "tradier_request_retry",
                    path=path,
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt == self._max_retries - 1:
                    raise
        return None

    async def get_expirations(self, ticker: str) -> list[date]:
        try:
            data = await self._request(
                "/markets/options/expirations",
                {"symbol": ticker.upper(), "includeAllRoots": "true"},
            )
        except Exception as e:
            logger.error("tradier_expirations_failed", ticker=ticker, error=str(e))
            return []

        expirations_data = data.get("expirations", {})
        raw_dates = expirations_data.get("date", [])
        if isinstance(raw_dates, str):
            raw_dates = [raw_dates]

        result: list[date] = []
        for d in raw_dates:
            try:
                result.append(date.fromisoformat(d))
            except ValueError:
                continue
        return sorted(result)

    async def get_options_chain(
        self, ticker: str, expirations: list[date] | None = None
    ) -> OptionsChainSnapshot:
        ticker = ticker.upper()

        if expirations is None:
            expirations = await self.get_expirations(ticker)

        all_options: list[OptionRecord] = []

        for exp in expirations:
            try:
                data = await self._request(
                    "/markets/options/chains",
                    {
                        "symbol": ticker,
                        "expiration": exp.isoformat(),
                        "greeks": "true",
                    },
                )
            except Exception as e:
                logger.warning(
                    "tradier_chain_fetch_failed",
                    ticker=ticker,
                    expiration=exp.isoformat(),
                    error=str(e),
                )
                continue

            options_data = data.get("options", {})
            raw_options = options_data.get("option", [])
            if isinstance(raw_options, dict):
                raw_options = [raw_options]
            if not isinstance(raw_options, list):
                continue

            for opt in raw_options:
                rec = self._parse_option(ticker, exp, opt)
                if rec:
                    all_options.append(rec)

        # Get spot price from a quote
        spot = 0.0
        try:
            quote_data = await self._request(
                "/markets/quotes", {"symbols": ticker}
            )
            quotes = quote_data.get("quotes", {}).get("quote", {})
            if isinstance(quotes, list):
                quotes = quotes[0] if quotes else {}
            spot = float(quotes.get("last", 0))
        except Exception:
            pass

        return OptionsChainSnapshot(
            ticker=ticker,
            spot_price=spot,
            snapshot_time=datetime.now(timezone.utc),
            options=all_options,
            expirations=expirations,
            meta=ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(timezone.utc),
                confidence_score=0.9 if all_options else 0.3,
            ),
        )

    def _parse_option(
        self, ticker: str, expiration: date, opt: dict[str, Any]
    ) -> OptionRecord | None:
        try:
            option_type = opt.get("option_type", "").lower()
            if option_type not in ("call", "put"):
                return None

            strike = float(opt["strike"])

            greeks = opt.get("greeks") or {}

            return OptionRecord(
                ticker=ticker,
                option_type=option_type,
                strike=strike,
                expiration=expiration,
                bid=_safe_float(opt.get("bid")),
                ask=_safe_float(opt.get("ask")),
                mid=_mid(opt.get("bid"), opt.get("ask")),
                last=_safe_float(opt.get("last")),
                volume=_safe_int(opt.get("volume")),
                open_interest=_safe_int(opt.get("open_interest")),
                implied_volatility=_safe_float(greeks.get("mid_iv")),
                delta=_safe_float(greeks.get("delta")),
                gamma=_safe_float(greeks.get("gamma")),
                theta=_safe_float(greeks.get("theta")),
                vega=_safe_float(greeks.get("vega")),
                rho=_safe_float(greeks.get("rho")),
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.debug("tradier_option_parse_failed", error=str(e))
            return None

    async def health_check(self) -> ProviderMeta:
        try:
            data = await self._request(
                "/markets/options/expirations",
                {"symbol": "AAPL"},
            )
            ok = "expirations" in (data or {})
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


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return f if f == f else None  # NaN check
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _mid(bid: Any, ask: Any) -> float | None:
    b = _safe_float(bid)
    a = _safe_float(ask)
    if b is not None and a is not None:
        return round((b + a) / 2, 4)
    return None
