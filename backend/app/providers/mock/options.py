from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime, timedelta

from app.providers.base import (
    OptionRecord,
    OptionsChainProvider,
    OptionsChainSnapshot,
    ProviderMeta,
)

MOCK_SPOT: dict[str, float] = {
    "SPY": 525.0, "QQQ": 445.0, "AAPL": 195.0, "MSFT": 420.0,
    "NVDA": 880.0, "AMZN": 185.0, "META": 510.0, "GOOGL": 165.0,
    "TSLA": 175.0, "AMD": 160.0, "NFLX": 625.0, "JPM": 200.0,
    "BAC": 38.0, "XOM": 115.0, "CVX": 160.0, "UNH": 520.0,
    "COST": 740.0, "AVGO": 1350.0, "PLTR": 24.0,
}

MOCK_BASE_IV: dict[str, float] = {
    "SPY": 0.14, "QQQ": 0.17, "AAPL": 0.22, "MSFT": 0.20,
    "NVDA": 0.38, "AMZN": 0.28, "META": 0.32, "GOOGL": 0.25,
    "TSLA": 0.55, "AMD": 0.42, "NFLX": 0.35, "JPM": 0.20,
    "BAC": 0.22, "XOM": 0.18, "CVX": 0.18, "UNH": 0.20,
    "COST": 0.18, "AVGO": 0.30, "PLTR": 0.60,
}


def _generate_expirations(today: date) -> list[date]:
    exps: list[date] = []
    for weeks_out in [1, 2, 3, 4, 5, 6, 8, 10, 13, 17, 26]:
        exp = today + timedelta(weeks=weeks_out)
        while exp.weekday() != 4:
            exp -= timedelta(days=1)
        if exp > today:
            exps.append(exp)
    return sorted(set(exps))


def _strike_ladder(spot: float) -> list[float]:
    if spot < 50:
        step = 1.0
    elif spot < 200:
        step = 2.5
    elif spot < 500:
        step = 5.0
    elif spot < 1000:
        step = 10.0
    else:
        step = 25.0
    center = round(spot / step) * step
    return [center + i * step for i in range(-10, 11)]


class MockOptionsProvider(OptionsChainProvider):
    def __init__(self, seed: int = 42) -> None:
        self._source = "mock_options"
        self._rng = random.Random(seed)

    def _price_option(
        self,
        spot: float,
        strike: float,
        dte: int,
        base_iv: float,
        option_type: str,
    ) -> OptionRecord:
        t = max(dte, 1) / 365.0
        iv = base_iv * (1 + 0.15 / max(math.sqrt(t * 365), 1))
        moneyness = math.log(spot / strike) if strike > 0 else 0
        intrinsic = max(0, spot - strike) if option_type == "CALL" else max(0, strike - spot)
        time_value = spot * iv * math.sqrt(t) * 0.4
        theo = max(intrinsic + time_value * math.exp(-moneyness**2 / (2 * iv**2 * t + 0.01)), 0.01)
        spread = max(0.05, theo * self._rng.uniform(0.02, 0.08))
        bid = round(max(0.01, theo - spread / 2), 2)
        ask = round(theo + spread / 2, 2)
        mid = round((bid + ask) / 2, 2)
        delta_sign = 1 if option_type == "CALL" else -1
        raw_delta = 0.5 + 0.5 * math.tanh(moneyness / (iv * math.sqrt(t) + 0.01))
        delta = round(delta_sign * raw_delta, 4)
        gamma = round(0.01 / (spot * iv * math.sqrt(t) + 0.01), 6)
        theta = round(-theo * iv / (2 * math.sqrt(t) + 0.01) / 365, 4)
        vega = round(spot * math.sqrt(t) * 0.01, 4)
        oi = int(self._rng.uniform(200, 15000))
        vol = int(self._rng.uniform(50, 5000))

        return OptionRecord(
            ticker="",
            option_type=option_type,
            strike=strike,
            expiration=date.today(),
            bid=bid,
            ask=ask,
            mid=mid,
            last=round(mid + self._rng.uniform(-spread * 0.3, spread * 0.3), 2),
            volume=vol,
            open_interest=oi,
            implied_volatility=round(iv, 4),
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            rho=round(strike * t * 0.01 * 0.01, 4),
        )

    async def get_options_chain(
        self, ticker: str, expirations: list[date] | None = None
    ) -> OptionsChainSnapshot:
        spot = MOCK_SPOT.get(ticker.upper(), 100.0)
        base_iv = MOCK_BASE_IV.get(ticker.upper(), 0.25)
        today = date.today()
        all_exps = _generate_expirations(today)
        target_exps = expirations if expirations else all_exps[:6]
        strikes = _strike_ladder(spot)
        options: list[OptionRecord] = []
        for exp in target_exps:
            dte = (exp - today).days
            for strike in strikes:
                for otype in ["CALL", "PUT"]:
                    rec = self._price_option(spot, strike, dte, base_iv, otype)
                    rec.ticker = ticker.upper()
                    rec.expiration = exp
                    rec.strike = strike
                    options.append(rec)
        return OptionsChainSnapshot(
            ticker=ticker.upper(),
            spot_price=spot,
            snapshot_time=datetime.now(UTC),
            options=options,
            expirations=all_exps,
            meta=ProviderMeta(
                source_name=self._source,
                freshness_timestamp=datetime.now(UTC),
                confidence_score=0.9,
            ),
        )

    async def get_expirations(self, ticker: str) -> list[date]:
        return _generate_expirations(date.today())

    async def health_check(self) -> ProviderMeta:
        return ProviderMeta(
            source_name=self._source,
            freshness_timestamp=datetime.now(UTC),
            confidence_score=1.0,
        )
