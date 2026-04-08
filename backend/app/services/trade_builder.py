from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.core.config import Settings
from app.core.enums import LegSide, OptionType, RecommendationClass
from app.core.logging import get_logger
from app.core.security import RISK_DISCLAIMER
from app.providers.base import (
    EarningsRecord,
    OptionsChainSnapshot,
    OptionRecord,
    PriceRecord,
    VolatilitySnapshot,
)
from app.providers.registry import ProviderRegistry
from app.services.liquidity import LiquidityEngine
from app.services.scoring import ScoringEngine

logger = get_logger(__name__)


@dataclass
class TradeLeg:
    leg_number: int
    option_type: OptionType
    side: LegSide
    strike: float
    expiration: date
    quantity: int = 1
    option: OptionRecord | None = None

    @property
    def bid(self) -> float | None:
        return self.option.bid if self.option else None

    @property
    def ask(self) -> float | None:
        return self.option.ask if self.option else None

    @property
    def mid(self) -> float | None:
        if self.option and self.option.bid is not None and self.option.ask is not None:
            return round((self.option.bid + self.option.ask) / 2, 4)
        return self.option.mid if self.option else None

    @property
    def debit(self) -> float:
        m = self.mid or 0.0
        return m if self.side == LegSide.BUY else -m

    @property
    def spread_to_mid(self) -> float | None:
        if self.option and self.option.bid is not None and self.option.ask is not None:
            mid = (self.option.bid + self.option.ask) / 2
            if mid > 0:
                return round((self.option.ask - self.option.bid) / mid, 4)
        return None


@dataclass
class ConstructedTrade:
    ticker: str
    spot_price: float
    earnings_date: date
    earnings_confidence: str
    entry_date_start: date
    entry_date_end: date
    planned_exit_date: date
    short_expiry: date
    long_expiry: date
    lower_strike: float
    upper_strike: float
    legs: list[TradeLeg]
    total_debit_mid: float
    total_debit_pessimistic: float
    estimated_max_loss: float
    profit_zone_low: float
    profit_zone_high: float
    classification: RecommendationClass = RecommendationClass.WATCHLIST
    overall_score: float = 0.0
    rationale_summary: str = ""
    key_risks: list[str] = field(default_factory=list)
    risk_disclaimer: str = RISK_DISCLAIMER


class TradeConstructionEngine:
    def __init__(self, settings: Settings, registry: ProviderRegistry) -> None:
        self._settings = settings
        self._registry = registry
        self._liquidity = LiquidityEngine(settings.liquidity)
        self._scoring = ScoringEngine(settings.scoring, settings.earnings_window)

    async def build_recommended(self, ticker: str) -> ConstructedTrade:
        earnings = await self._registry.earnings.get_earnings_date(ticker)
        if earnings is None:
            raise ValueError(f"No earnings date for {ticker}")

        price = await self._registry.price.get_current_price(ticker)
        if price is None:
            raise ValueError(f"No price data for {ticker}")

        chain = await self._registry.options.get_options_chain(ticker)
        vol = await self._registry.volatility.get_volatility_metrics(ticker)

        return self._construct(ticker, earnings, price, chain, vol)

    async def build_custom(
        self,
        ticker: str,
        lower_strike: float | None = None,
        upper_strike: float | None = None,
        short_expiry: date | None = None,
        long_expiry: date | None = None,
    ) -> ConstructedTrade:
        earnings = await self._registry.earnings.get_earnings_date(ticker)
        if earnings is None:
            raise ValueError(f"No earnings date for {ticker}")

        price = await self._registry.price.get_current_price(ticker)
        if price is None:
            raise ValueError(f"No price data for {ticker}")

        chain = await self._registry.options.get_options_chain(ticker)
        vol = await self._registry.volatility.get_volatility_metrics(ticker)

        return self._construct(
            ticker, earnings, price, chain, vol,
            override_lower=lower_strike,
            override_upper=upper_strike,
            override_short_exp=short_expiry,
            override_long_exp=long_expiry,
        )

    def _construct(
        self,
        ticker: str,
        earnings: EarningsRecord,
        price: PriceRecord,
        chain: OptionsChainSnapshot,
        vol: VolatilitySnapshot,
        override_lower: float | None = None,
        override_upper: float | None = None,
        override_short_exp: date | None = None,
        override_long_exp: date | None = None,
    ) -> ConstructedTrade:
        spot = price.close
        today = date.today()
        days_to = (earnings.earnings_date - today).days
        exit_date = earnings.earnings_date - timedelta(
            days=self._settings.earnings_window.EXIT_DAYS_BEFORE_EARNINGS
        )

        # Select expirations
        expirations = sorted(chain.expirations)
        short_exp = override_short_exp or self._select_short_expiry(expirations, earnings.earnings_date)
        long_exp = override_long_exp or self._select_long_expiry(expirations, short_exp)

        # Estimate expected move for strike placement
        front_iv = vol.front_expiry_iv or 0.25
        estimated_move = spot * front_iv * (days_to / 365) ** 0.5

        # Select strikes
        lower = override_lower or self._snap_strike(spot - estimated_move * 0.8, chain, short_exp, long_exp)
        upper = override_upper or self._snap_strike(spot + estimated_move * 0.8, chain, short_exp, long_exp)

        # Ensure lower < upper
        if lower >= upper:
            short_strikes = {o.strike for o in chain.options if o.expiration == short_exp}
            long_strikes = {o.strike for o in chain.options if o.expiration == long_exp}
            valid_strikes = sorted(short_strikes.intersection(long_strikes))
            if not valid_strikes:
                valid_strikes = sorted({o.strike for o in chain.options})
                
            atm_idx = min(range(len(valid_strikes)), key=lambda i: abs(valid_strikes[i] - spot)) if valid_strikes else 0
            if atm_idx > 0 and atm_idx < len(valid_strikes) - 1:
                lower = valid_strikes[max(0, atm_idx - 2)]
                upper = valid_strikes[min(len(valid_strikes) - 1, atm_idx + 2)]

        # Build 4 legs
        legs = self._build_legs(ticker, lower, upper, short_exp, long_exp, chain)

        # Calculate pricing
        total_debit = sum(l.debit for l in legs)
        total_debit_pessimistic = self._pessimistic_debit(legs)

        # Profit zone estimation
        profit_zone_low = round(lower - estimated_move * 0.3, 2)
        profit_zone_high = round(upper + estimated_move * 0.3, 2)

        # Score the trade
        full_liq = self._liquidity.evaluate_full(price, chain, short_exp, long_exp)
        scoring_result = self._scoring.score(
            ticker=ticker,
            earnings=earnings,
            price=price,
            vol=vol,
            chain=chain,
            liquidity=full_liq,
        )

        key_risks = [
            "Earnings date may change — verify before entry",
            "Stock may move outside profit zone before exit",
            "IV expansion may not materialize as expected",
            "Bid-ask spreads may widen at execution",
        ]
        if earnings.confidence != "CONFIRMED":
            key_risks.insert(0, f"Earnings date is {earnings.confidence} — high change risk")
        if total_debit > spot * 0.03:
            key_risks.append(f"Total debit ${total_debit:.2f} is >3% of spot — consider sizing down")

        rationale = (
            f"Double calendar on {ticker} with earnings in {days_to}d. "
            f"Lower calendar at ${lower:.0f}, upper at ${upper:.0f}. "
            f"Short expiry {short_exp}, long expiry {long_exp}. "
            f"Total debit ~${total_debit:.2f}. Exit planned for {exit_date}. "
            f"Score: {scoring_result.overall_score}/100."
        )

        return ConstructedTrade(
            ticker=ticker,
            spot_price=spot,
            earnings_date=earnings.earnings_date,
            earnings_confidence=earnings.confidence,
            entry_date_start=today,
            entry_date_end=today + timedelta(days=2),
            planned_exit_date=exit_date,
            short_expiry=short_exp,
            long_expiry=long_exp,
            lower_strike=lower,
            upper_strike=upper,
            legs=legs,
            total_debit_mid=round(total_debit, 2),
            total_debit_pessimistic=round(total_debit_pessimistic, 2),
            estimated_max_loss=round(abs(total_debit), 2),
            profit_zone_low=profit_zone_low,
            profit_zone_high=profit_zone_high,
            classification=scoring_result.classification,
            overall_score=scoring_result.overall_score,
            rationale_summary=rationale,
            key_risks=key_risks,
        )

    def _select_short_expiry(self, expirations: list[date], earnings_date: date) -> date:
        # Short expiry: first expiry on or after earnings (sell theta-rich short-dated)
        candidates = [e for e in expirations if e >= earnings_date]
        if candidates:
            return candidates[0]
        return expirations[-1] if expirations else earnings_date

    def _select_long_expiry(self, expirations: list[date], short_expiry: date) -> date:
        # Long expiry: at least 14 days after short expiry (buy longer-dated protection)
        min_gap = timedelta(days=14)
        candidates = [e for e in expirations if e >= short_expiry + min_gap]
        if candidates:
            return candidates[0]
        return short_expiry + timedelta(days=28)

    def _snap_strike(self, target: float, chain: OptionsChainSnapshot, short_exp: date, long_exp: date) -> float:
        short_strikes = {o.strike for o in chain.options if o.expiration == short_exp}
        long_strikes = {o.strike for o in chain.options if o.expiration == long_exp}
        valid_strikes = sorted(short_strikes.intersection(long_strikes))
        
        if not valid_strikes:
            # Fallback to any strike if no overlap
            strikes = sorted({o.strike for o in chain.options})
            if not strikes:
                return round(target, 0)
            return min(strikes, key=lambda s: abs(s - target))
            
        return min(valid_strikes, key=lambda s: abs(s - target))

    def _build_legs(
        self,
        ticker: str,
        lower: float,
        upper: float,
        short_exp: date,
        long_exp: date,
        chain: OptionsChainSnapshot,
    ) -> list[TradeLeg]:
        configs = [
            (1, OptionType.PUT, LegSide.SELL, lower, short_exp),    # Sell short put
            (2, OptionType.PUT, LegSide.BUY, lower, long_exp),      # Buy long put
            (3, OptionType.CALL, LegSide.SELL, upper, short_exp),    # Sell short call
            (4, OptionType.CALL, LegSide.BUY, upper, long_exp),     # Buy long call
        ]
        legs = []
        for leg_num, otype, side, strike, exp in configs:
            opt = self._find_option(chain, strike, exp, otype.value)
            legs.append(TradeLeg(
                leg_number=leg_num,
                option_type=otype,
                side=side,
                strike=strike,
                expiration=exp,
                option=opt,
            ))
        return legs

    def _find_option(
        self, chain: OptionsChainSnapshot, strike: float, exp: date, otype: str
    ) -> OptionRecord | None:
        otype_lower = otype.lower()
        for o in chain.options:
            if o.strike == strike and o.expiration == exp and o.option_type.lower() == otype_lower:
                return o
        return None

    def _pessimistic_debit(self, legs: list[TradeLeg]) -> float:
        total = 0.0
        for l in legs:
            if l.side == LegSide.BUY:
                total += l.ask or (l.mid or 0.0)
            else:
                total -= l.bid or (l.mid or 0.0)
        return total
