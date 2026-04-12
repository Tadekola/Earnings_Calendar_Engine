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

    async def get_volatility_metrics(self, ticker: str) -> VolatilitySnapshot:
        today = date.today()
        start = today - timedelta(days=60)

        # Fetch price history for realized vol
        history = await self._price.get_price_history(ticker, start, today)

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

            # IV rank: percentile of ATM IV within the chain's
            # full IV distribution (0 = lowest, 1 = highest)
            all_ivs = sorted([
                o.implied_volatility
                for o in chain.options
                if o.implied_volatility is not None
                and o.implied_volatility > 0
            ])
            atm_iv = front_iv or back_iv
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
