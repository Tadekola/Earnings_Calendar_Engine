"""TastyTrade provider — authoritative source for IV Rank, IV Percentile,
per-expiry ATM IV, historical volatility, and liquidity rating via the
`/market-metrics` endpoint.

Architecture:
    TastyTradeClient         OAuth access-token manager + HTTP client
    TastyTradeVolatilityProvider
                             Implements VolatilityMetricsProvider:
                             - IVR, IVP, HV-30/60/90 from TT
                             - Term structure slope from TT per-expiry IV
                             - ATR from fallback (price history based)

The fallback provider (typically ComputedVolatilityProvider) is still
consulted for metrics TT doesn't expose (ATR 14d, realized_vol_10d/20d),
so we get the best of both.

Credentials come from env via TastyTradeSettings (TT_CLIENT_ID,
TT_CLIENT_SECRET, TT_REFRESH_TOKEN). Access tokens are short-lived
(~15 min) and auto-refreshed on expiry.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx

from app.core.config import TastyTradeSettings
from app.core.logging import get_logger
from app.providers.base import (
    ProviderMeta,
    VolatilityMetricsProvider,
    VolatilitySnapshot,
)

logger = get_logger(__name__)

TT_API_BASE = "https://api.tastytrade.com"
_TOKEN_REFRESH_MARGIN_SECONDS = 60  # refresh 1 min before actual expiry
_METRICS_CACHE_TTL_SECONDS = 300     # 5-min cache per symbol


@dataclass
class _CachedMetrics:
    fetched_at: datetime
    data: dict


class TastyTradeClient:
    """Thin async client for TastyTrade REST API.

    Handles:
      * OAuth access-token acquisition via refresh_token grant
      * Auto-refresh on expiry
      * `/market-metrics` batched lookup with per-symbol cache
    """

    def __init__(self, settings: TastyTradeSettings, http_timeout: float = 15.0):
        self._settings = settings
        self._timeout = http_timeout
        self._access_token: str | None = None
        self._token_expires_at: datetime = datetime.min.replace(tzinfo=UTC)
        self._token_lock = asyncio.Lock()
        self._cache: dict[str, _CachedMetrics] = {}

    @property
    def is_configured(self) -> bool:
        return bool(
            self._settings.TT_CLIENT_ID
            and self._settings.TT_CLIENT_SECRET
            and self._settings.TT_REFRESH_TOKEN
        )

    async def _ensure_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        now = datetime.now(UTC)
        if (
            self._access_token
            and now < self._token_expires_at - timedelta(seconds=_TOKEN_REFRESH_MARGIN_SECONDS)
        ):
            return self._access_token

        async with self._token_lock:
            # Re-check after acquiring lock (another coroutine may have refreshed)
            if (
                self._access_token
                and datetime.now(UTC)
                < self._token_expires_at - timedelta(seconds=_TOKEN_REFRESH_MARGIN_SECONDS)
            ):
                return self._access_token

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(
                    f"{TT_API_BASE}/oauth/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self._settings.TT_REFRESH_TOKEN,
                        "client_id": self._settings.TT_CLIENT_ID,
                        "client_secret": self._settings.TT_CLIENT_SECRET,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            if r.status_code != 200:
                logger.error(
                    "tastytrade_oauth_failed",
                    status=r.status_code,
                    body=r.text[:300],
                )
                r.raise_for_status()

            body = r.json()
            self._access_token = body["access_token"]
            expires_in = int(body.get("expires_in", 900))
            self._token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
            logger.info(
                "tastytrade_token_refreshed",
                expires_in_seconds=expires_in,
            )
            return self._access_token

    async def get_market_metrics(
        self, tickers: list[str], force: bool = False
    ) -> dict[str, dict]:
        """Fetch /market-metrics for one or more symbols. Returns dict keyed by
        uppercase symbol. Respects a short per-symbol cache unless ``force``.
        """
        tickers = [t.upper() for t in tickers]
        now = datetime.now(UTC)
        to_fetch: list[str] = []
        out: dict[str, dict] = {}

        if not force:
            for t in tickers:
                cached = self._cache.get(t)
                if (
                    cached
                    and (now - cached.fetched_at).total_seconds() < _METRICS_CACHE_TTL_SECONDS
                ):
                    out[t] = cached.data
                else:
                    to_fetch.append(t)
        else:
            to_fetch = list(tickers)

        if not to_fetch:
            return out

        token = await self._ensure_token()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(
                f"{TT_API_BASE}/market-metrics",
                params={"symbols": ",".join(to_fetch)},
                headers={"Authorization": f"Bearer {token}"},
            )
        if r.status_code == 401:
            # Token may have been invalidated server-side; force refresh and retry once
            logger.warning("tastytrade_401_retry")
            self._access_token = None
            token = await self._ensure_token()
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(
                    f"{TT_API_BASE}/market-metrics",
                    params={"symbols": ",".join(to_fetch)},
                    headers={"Authorization": f"Bearer {token}"},
                )
        if r.status_code != 200:
            logger.error(
                "tastytrade_market_metrics_failed",
                status=r.status_code,
                body=r.text[:300],
                tickers=to_fetch,
            )
            r.raise_for_status()

        items = r.json().get("data", {}).get("items", [])
        for it in items:
            sym = (it.get("symbol") or "").upper()
            if not sym:
                continue
            out[sym] = it
            self._cache[sym] = _CachedMetrics(fetched_at=now, data=it)

        # Symbols that TT didn't return (delisted / unsupported) — log once
        missing = [t for t in to_fetch if t not in out]
        if missing:
            logger.warning("tastytrade_symbols_missing", tickers=missing)

        return out

    async def health_check(self) -> ProviderMeta:
        if not self.is_configured:
            return ProviderMeta(
                source_name="tastytrade",
                error_details="credentials missing",
                confidence_score=0.0,
            )
        try:
            await self._ensure_token()
            return ProviderMeta(
                source_name="tastytrade",
                freshness_timestamp=datetime.now(UTC),
                confidence_score=1.0,
            )
        except Exception as e:
            return ProviderMeta(
                source_name="tastytrade",
                error_details=str(e)[:200],
                confidence_score=0.0,
            )


class TastyTradeVolatilityProvider(VolatilityMetricsProvider):
    """Volatility provider that pulls authoritative IVR/IVP/HV from
    TastyTrade and delegates missing fields (ATR, short-window RV) to a
    fallback (typically ComputedVolatilityProvider)."""

    def __init__(
        self,
        client: TastyTradeClient,
        fallback: VolatilityMetricsProvider,
    ):
        self._client = client
        self._fallback = fallback

    async def get_volatility_metrics(self, ticker: str) -> VolatilitySnapshot:
        ticker_u = ticker.upper()
        today = date.today()

        # Always compute the fallback — cheap when cached, and we need it
        # for ATR / short-window RV which TT doesn't provide.
        fallback_snap = await self._fallback.get_volatility_metrics(ticker)

        try:
            tt_map = await self._client.get_market_metrics([ticker_u])
        except Exception as e:
            logger.warning(
                "tastytrade_fallback_to_computed",
                ticker=ticker_u,
                error=str(e)[:200],
            )
            # Graceful degradation — return the fallback snapshot unchanged
            return fallback_snap

        item = tt_map.get(ticker_u)
        if not item:
            logger.info("tastytrade_no_metrics_returned", ticker=ticker_u)
            return fallback_snap

        iv_rank = _safe_float(item.get("implied-volatility-index-rank"))
        iv_pct = _safe_float(item.get("implied-volatility-percentile"))
        # HV fields come back as percents (e.g. 11.21 meaning 11.21%); divide by 100
        hv_30 = _safe_hv_percent(item.get("historical-volatility-30-day"))
        hv_60 = _safe_hv_percent(item.get("historical-volatility-60-day"))
        hv_90 = _safe_hv_percent(item.get("historical-volatility-90-day"))

        # Per-expiration ATM IV: pick front (≥7d out) and back (≥28d)
        front_iv, back_iv, term_slope = _term_structure_from_tt(
            item.get("option-expiration-implied-volatilities") or [], today
        )

        # Blend: TT values where available, fallback otherwise
        return VolatilitySnapshot(
            ticker=ticker_u,
            as_of_date=today,
            realized_vol_10d=fallback_snap.realized_vol_10d,
            realized_vol_20d=fallback_snap.realized_vol_20d,
            realized_vol_30d=hv_30 if hv_30 is not None else fallback_snap.realized_vol_30d,
            atr_14d=fallback_snap.atr_14d,
            iv_rank=iv_rank if iv_rank is not None else fallback_snap.iv_rank,
            iv_percentile=iv_pct if iv_pct is not None else fallback_snap.iv_percentile,
            front_expiry_iv=front_iv if front_iv is not None else fallback_snap.front_expiry_iv,
            back_expiry_iv=back_iv if back_iv is not None else fallback_snap.back_expiry_iv,
            term_structure_slope=term_slope
            if term_slope is not None
            else fallback_snap.term_structure_slope,
            meta=ProviderMeta(
                source_name="tastytrade_market_metrics",
                freshness_timestamp=datetime.now(UTC),
                confidence_score=0.95,
                provenance={
                    "iv_rank_source": "tastytrade" if iv_rank is not None else "fallback",
                    "hv_30_source": "tastytrade" if hv_30 is not None else "fallback",
                    "term_slope_source": "tastytrade" if term_slope is not None else "fallback",
                    "hv_60": hv_60,
                    "hv_90": hv_90,
                    "liquidity_rank": _safe_float(item.get("liquidity-rank")),
                    "liquidity_rating": item.get("liquidity-rating"),
                    "beta": _safe_float(item.get("beta")),
                },
            ),
        )

    async def health_check(self) -> ProviderMeta:
        return await self._client.health_check()


# ── helpers ──────────────────────────────────────────────────────────────────


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_hv_percent(v) -> float | None:
    """TT returns HV as percent (11.21 meaning 11.21%). Normalize to 0..1."""
    f = _safe_float(v)
    if f is None:
        return None
    # Sanity: if it's already in 0..1 form leave alone; otherwise divide
    return f / 100.0 if f > 3.0 else f


def _term_structure_from_tt(
    entries: list[dict], today: date
) -> tuple[float | None, float | None, float | None]:
    """Select front (≥7d) and back (≥28d) ATM IV from TT's per-expiration list
    and compute the term-structure slope.

    TT entries look like:
        {"expiration-date": "2026-04-24", "implied-volatility": 0.29, ...}

    Returns (front_iv, back_iv, slope) with slope convention
    (back_iv - front_iv) / back_iv (positive = contango).
    """
    parsed: list[tuple[date, float]] = []
    for e in entries:
        exp_s = e.get("expiration-date")
        iv = _safe_float(e.get("implied-volatility"))
        if not exp_s or iv is None or iv <= 0:
            continue
        try:
            exp = date.fromisoformat(exp_s)
        except ValueError:
            continue
        if exp > today:
            parsed.append((exp, iv))

    if not parsed:
        return None, None, None

    parsed.sort(key=lambda p: p[0])

    def _pick(min_days: int) -> tuple[date, float] | None:
        for exp, iv in parsed:
            if (exp - today).days >= min_days:
                return exp, iv
        return None

    front = _pick(7) or parsed[0]
    back = _pick(28) or (parsed[-1] if parsed[-1][0] != front[0] else None)

    front_iv = front[1] if front else None
    back_iv = back[1] if back else None
    slope: float | None = None
    if front_iv is not None and back_iv is not None and back_iv > 0:
        slope = round((back_iv - front_iv) / back_iv, 4)
    return front_iv, back_iv, slope
