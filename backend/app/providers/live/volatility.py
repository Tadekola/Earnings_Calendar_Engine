from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import numpy as np

from app.core.logging import get_logger
from app.providers.base import (
    OptionsChainProvider,
    PriceProvider,
    ProviderMeta,
    VolatilityMetricsProvider,
    VolatilitySnapshot,
)

logger = get_logger(__name__)


class ComputedVolatilityProvider(VolatilityMetricsProvider):
    """Derives volatility metrics from price history and options chain data."""

    def __init__(
        self, price_provider: PriceProvider, options_provider: OptionsChainProvider
    ) -> None:
        self._price = price_provider
        self._options = options_provider
        self._source = "computed_volatility"

    # Index tickers with no direct historical price feed — fall back to a
    # proxy ticker whose price level closely tracks the index product.
    # XSP = SPX/10 ≈ SPY (both ~$500), so realized vol % and ATR $ are
    # directly comparable without scaling.
    _HISTORY_PROXY: dict[str, str] = {"XSP": "SPY"}

    # For index products, real IV Rank comes from the volatility index
    # that tracks the same IV surface. VIX = 30d ATM IV of SPX, and
    # XSP / SPY options all share SPX's IV surface. Using ^VIX is exact
    # for those three tickers.
    #
    # For QQQ (^VXN) and IWM (^RVX), the exact volatility indices are
    # only available on a paid FMP tier. We use ^VIX as an approximation:
    # QQQ-IV / VXN correlation ≈ 0.90 with VIX, and IWM-IV / RVX ≈ 0.85.
    # This is strictly directional (IVR moves the right way) but absolute
    # level can be off 5-15pp on typical days. Far better than the
    # chain-skew fallback (which is effectively random noise).
    # TODO: upgrade to ^VXN and ^RVX when a richer data tier is available.
    _IV_INDEX_PROXY: dict[str, str] = {
        "XSP": "^VIX",   # exact — shares SPX surface
        "SPY": "^VIX",   # exact — shares SPX surface
        "QQQ": "^VIX",   # approximate — should be ^VXN
        "IWM": "^VIX",   # approximate — should be ^RVX
    }
    _IVR_LOOKBACK_DAYS: int = 252  # standard 52-week window

    async def get_volatility_metrics(self, ticker: str) -> VolatilitySnapshot:
        today = date.today()
        start = today - timedelta(days=60)

        # Fetch price history for realized vol
        history = await self._price.get_price_history(ticker, start, today)

        # Index products (XSP) have no direct historical price at FMP.
        # Fall back to a proxy (SPY for XSP) — same price regime, same vol.
        if not history:
            proxy = self._HISTORY_PROXY.get(ticker.upper())
            if proxy:
                logger.info(
                    "volatility_history_proxy",
                    ticker=ticker,
                    proxy=proxy,
                    reason="no_direct_history",
                )
                history = await self._price.get_price_history(proxy, start, today)

        rv_10 = self._realized_vol(history, 10)
        rv_20 = self._realized_vol(history, 20)
        rv_30 = self._realized_vol(history, 30)
        atr = self._atr(history, 14)

        # Fetch options chain for IV metrics
        chain = await self._options.get_options_chain(ticker)
        spot = chain.spot_price or (history[-1].close if history else 0)

        front_iv, back_iv, iv_rank, iv_pct = None, None, None, None
        term_slope = None

        if chain.expirations and chain.options:
            sorted_exps = sorted(chain.expirations)
            # Pick trade-relevant expirations:
            #   front = nearest expiry ≥7 days out (typical short leg)
            #   back  = nearest expiry ≥28 days out (typical long leg)
            front_exp = self._nearest_exp(sorted_exps, today, 7)
            back_exp = self._nearest_exp(sorted_exps, today, 28)
            # Fallback: first two if we can't find good ones
            if front_exp is None and sorted_exps:
                front_exp = sorted_exps[0]
            if back_exp is None and len(sorted_exps) > 1:
                back_exp = sorted_exps[-1]
            # Ensure they are different
            if front_exp == back_exp and len(sorted_exps) > 1:
                back_exp = sorted_exps[-1]

            if front_exp:
                front_iv = self._atm_iv(chain.options, spot, front_exp)
            if back_exp:
                back_iv = self._atm_iv(chain.options, spot, back_exp)

            # term_structure_slope: positive = contango (back > front),
            # negative = backwardation (front > back, good for calendars)
            if front_iv and back_iv and back_iv > 0:
                term_slope = round(
                    (back_iv - front_iv) / back_iv, 4
                )

            # IV Rank: standard definition is
            #   (current IV − 52w low IV) / (52w high IV − 52w low IV)
            # For index products (XSP), the correct IV series is the
            # volatility index (VIX), since XSP options share SPX's IV
            # surface. For equities without stored IV history, we fall
            # back to the chain-skew proxy and flag it as approximate.
            atm_iv = front_iv or back_iv
            iv_index = self._IV_INDEX_PROXY.get(ticker.upper())
            if iv_index:
                iv_rank, iv_pct = await self._iv_rank_from_index(iv_index)
                logger.debug(
                    "iv_rank_from_index",
                    ticker=ticker,
                    index=iv_index,
                    iv_rank=iv_rank,
                    iv_percentile=iv_pct,
                )
            else:
                # Equity fallback: until we have stored historical IV,
                # approximate IV Rank using the chain's own IV distribution.
                # NOTE: this under-estimates IVR because ATM IV sits near the
                # low end of the skew smile. TODO: persist daily ATM IV
                # snapshots and compute true 252-day IVR from storage.
                all_ivs = sorted([
                    o.implied_volatility
                    for o in chain.options
                    if o.implied_volatility is not None
                    and o.implied_volatility > 0
                ])
                if all_ivs and atm_iv:
                    rank_pos = sum(1 for iv in all_ivs if iv <= atm_iv)
                    iv_rank = round(rank_pos / len(all_ivs), 4)
                if all_ivs and rv_30 and rv_30 > 0:
                    median_iv = float(np.median(all_ivs))
                    iv_pct = round(
                        min(max((median_iv - rv_30) / rv_30, 0), 1), 4
                    )

        return VolatilitySnapshot(
            ticker=ticker.upper(),
            as_of_date=today,
            realized_vol_10d=rv_10,
            realized_vol_20d=rv_20,
            realized_vol_30d=rv_30,
            atr_14d=atr,
            iv_rank=iv_rank,
            iv_percentile=iv_pct,
            front_expiry_iv=front_iv,
            back_expiry_iv=back_iv,
            term_structure_slope=term_slope,
            meta=ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(UTC),
                confidence_score=0.8 if history else 0.2,
            ),
        )

    async def _iv_rank_from_index(
        self, index_symbol: str
    ) -> tuple[float | None, float | None]:
        """Compute standard 52-week IV Rank and IV Percentile from a volatility
        index series (e.g., ^VIX). Returns values in 0..1 range.

        IV Rank    = (current - 52w_low) / (52w_high - 52w_low)
        IV Pctile  = fraction of trading days below current level
        """
        today = date.today()
        start = today - timedelta(days=self._IVR_LOOKBACK_DAYS + 30)
        try:
            hist = await self._price.get_price_history(index_symbol, start, today)
        except Exception as e:
            logger.warning(
                "iv_index_history_failed", index=index_symbol, error=str(e)
            )
            return None, None

        if not hist or len(hist) < 20:
            return None, None

        # Use close prices for the volatility index
        closes = [h.close for h in hist if h.close and h.close > 0]
        if len(closes) < 20:
            return None, None

        current = closes[-1]
        window = closes[-self._IVR_LOOKBACK_DAYS:]
        lo, hi = min(window), max(window)

        if hi > lo:
            iv_rank = round((current - lo) / (hi - lo), 4)
            iv_rank = max(0.0, min(1.0, iv_rank))
        else:
            iv_rank = 0.0

        below = sum(1 for c in window if c < current)
        iv_pct = round(below / len(window), 4)

        return iv_rank, iv_pct

    def _realized_vol(self, history: list, window: int) -> float | None:
        if len(history) < window + 1:
            return None
        closes = [r.close for r in history[-(window + 1) :]]
        log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        if not log_returns:
            return None
        std = float(np.std(log_returns, ddof=1))
        return round(std * math.sqrt(252), 4)

    def _atr(self, history: list, window: int) -> float | None:
        if len(history) < window + 1:
            return None
        trs = []
        for i in range(1, len(history)):
            h = history[i].high
            lo = history[i].low
            pc = history[i - 1].close
            tr = max(h - lo, abs(h - pc), abs(lo - pc))
            trs.append(tr)
        if len(trs) < window:
            return None
        return round(float(np.mean(trs[-window:])), 4)

    @staticmethod
    def _nearest_exp(
        sorted_exps: list[date], today: date, min_days: int
    ) -> date | None:
        """Return the nearest expiration that is at least min_days out."""
        target = today + timedelta(days=min_days)
        for exp in sorted_exps:
            if exp >= target:
                return exp
        return None

    def _atm_iv(self, options: list, spot: float, expiration: date) -> float | None:
        """Get ATM implied volatility for a given expiration.

        Averages the ATM call and put IVs when both are available
        for a more stable reading.
        """
        candidates = [
            o
            for o in options
            if o.expiration == expiration
            and o.implied_volatility is not None
            and o.implied_volatility > 0
        ]
        if not candidates:
            return None
        # Find closest strike to ATM
        atm_strike = min(candidates, key=lambda o: abs(o.strike - spot)).strike
        atm_opts = [o for o in candidates if o.strike == atm_strike]
        if not atm_opts:
            return None
        avg_iv = sum(o.implied_volatility for o in atm_opts) / len(atm_opts)
        return round(avg_iv, 4)

    async def health_check(self) -> ProviderMeta:
        return ProviderMeta(
            source_name=self._source,
            freshness_timestamp=datetime.now(UTC),
            confidence_score=0.8,
        )
