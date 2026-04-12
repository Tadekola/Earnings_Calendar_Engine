from __future__ import annotations

from datetime import date, timedelta

from app.core.config import Settings
from app.core.enums import LegSide, OptionType, RecommendationClass
from app.providers.base import (
    EarningsRecord,
    OptionRecord,
    OptionsChainSnapshot,
    PriceRecord,
    VolatilitySnapshot,
)
from app.services.base_strategy import BaseOptionsStrategy
from app.services.liquidity import LiquidityCheckResult, LiquidityEngine
from app.services.scoring import ScoreFactor, ScoringEngine, ScoringResult
from app.services.trade_builder import ConstructedTrade, TradeLeg


class DoubleCalendarStrategy(BaseOptionsStrategy):
    """
    Standard Double Calendar options strategy.
    Sells front-month IV, buys back-month IV.
    """

    def __init__(self, settings: Settings, registry) -> None:
        super().__init__(settings, registry)
        self._liquidity = LiquidityEngine(settings.liquidity)
        self._scoring = ScoringEngine(settings.scoring, settings.earnings_window)

    @property
    def strategy_type(self) -> str:
        return "DOUBLE_CALENDAR"

    def validate_liquidity(
        self,
        price: PriceRecord,
        chain: OptionsChainSnapshot,
        short_exp: date,
        long_exp: date,
    ) -> LiquidityCheckResult:
        return self._liquidity.evaluate_full(price, chain, short_exp, long_exp)

    def calculate_score(
        self,
        ticker: str,
        earnings: EarningsRecord | None,
        price: PriceRecord,
        vol: VolatilitySnapshot,
        chain: OptionsChainSnapshot,
        liquidity: LiquidityCheckResult,
    ) -> ScoringResult:
        scoring_result = self._scoring.score(
            ticker=ticker,
            earnings=earnings,
            price=price,
            vol=vol,
            chain=chain,
            liquidity=liquidity,
        )

        factors = scoring_result.factors

        # Append strategy-specific risk factor
        factors.append(
            ScoreFactor(
                name="Capital Preservation Buffer",
                weight=10.0,
                raw_score=100.0,
                weighted_score=0.0,  # will be normalized below
                rationale="Double Calendars retain back-month extrinsic value.",
            )
        )

        # Regime Filter Bonus
        front_iv = vol.front_expiry_iv or 0.0
        back_iv = vol.back_expiry_iv or 0.0
        in_backwardation = front_iv > back_iv * 1.10  # > 10%

        if in_backwardation:
            scoring_result.factors.append(
                ScoreFactor(
                    name="Regime Filter",
                    weight=10.0,
                    raw_score=100.0,
                    weighted_score=0.0,  # will be normalized below
                    rationale="IV Backwardation regime detected. +10 bonus for Double Calendar.",
                )
            )

        # Re-normalize all weighted_scores using actual total weight
        total_weight = sum(f.weight for f in scoring_result.factors)
        if total_weight > 0:
            for f in scoring_result.factors:
                f.weighted_score = round(f.raw_score * (f.weight / total_weight), 2)

        scoring_result.overall_score = min(
            100.0, sum(f.weighted_score for f in scoring_result.factors)
        )

        if scoring_result.overall_score >= self._settings.scoring.RECOMMEND_THRESHOLD:
            scoring_result.classification = RecommendationClass.RECOMMEND
        elif scoring_result.overall_score >= self._settings.scoring.WATCHLIST_THRESHOLD:
            scoring_result.classification = RecommendationClass.WATCHLIST

        days_to = (earnings.earnings_date - date.today()).days if earnings else 0
        scoring_result.rationale_summary = self._scoring._build_rationale(
            ticker,
            scoring_result.overall_score,
            scoring_result.classification,
            scoring_result.factors,
            days_to,
            earnings,
        )

        if in_backwardation:
            scoring_result.rationale_summary += " (+10 bonus for IV Backwardation regime)"

        return scoring_result

    def build_trade_structure(
        self,
        ticker: str,
        earnings: EarningsRecord | None,
        price: PriceRecord,
        vol: VolatilitySnapshot,
        chain: OptionsChainSnapshot,
        override_lower: float | None = None,
        override_upper: float | None = None,
        override_short_exp: date | None = None,
        override_long_exp: date | None = None,
    ) -> ConstructedTrade:
        spot = chain.spot_price or price.close
        today = date.today()

        # Step 1: Select Expirations
        earnings_date = earnings.earnings_date if earnings else today + timedelta(days=1)
        days_to = (earnings_date - today).days if earnings else 0

        expirations = sorted(chain.expirations)
        short_exp = override_short_exp or self._select_short_expiry(expirations, earnings_date)
        long_exp = override_long_exp or self._select_long_expiry(expirations, short_exp)

        front_iv = vol.front_expiry_iv or 0.25
        # Floor at 1 day to avoid zero-width strikes at DTE=0
        dte_for_move = max(days_to, 1)
        estimated_move = spot * front_iv * (dte_for_move / 365) ** 0.5

        lower = override_lower or self._snap_strike(
            spot - estimated_move * 0.8, chain, short_exp, long_exp
        )
        upper = override_upper or self._snap_strike(
            spot + estimated_move * 0.8, chain, short_exp, long_exp
        )

        if lower >= upper:
            short_strikes = {o.strike for o in chain.options if o.expiration == short_exp}
            long_strikes = {o.strike for o in chain.options if o.expiration == long_exp}
            valid_strikes = sorted(short_strikes.intersection(long_strikes))
            if not valid_strikes:
                valid_strikes = sorted({o.strike for o in chain.options})

            atm_idx = (
                min(range(len(valid_strikes)), key=lambda i: abs(valid_strikes[i] - spot))
                if valid_strikes
                else 0
            )
            if atm_idx > 0 and atm_idx < len(valid_strikes) - 1:
                lower = valid_strikes[max(0, atm_idx - 2)]
                upper = valid_strikes[min(len(valid_strikes) - 1, atm_idx + 2)]

        legs = self._build_legs(ticker, lower, upper, short_exp, long_exp, chain)

        total_debit = sum(leg.debit for leg in legs)
        total_debit_pessimistic = self._pessimistic_debit(legs)

        profit_zone_low = round(lower - estimated_move * 0.3, 2)
        profit_zone_high = round(upper + estimated_move * 0.3, 2)

        full_liq = self.validate_liquidity(price, chain, short_exp, long_exp)
        scoring_result = self.calculate_score(ticker, earnings, price, vol, chain, full_liq)

        key_risks = [
            "Earnings date may change — verify before entry",
            "Stock may move outside profit zone before exit",
            "IV expansion may not materialize as expected",
            "Bid-ask spreads may widen at execution",
        ]
        if earnings and earnings.confidence != "CONFIRMED":
            key_risks.insert(0, f"Earnings date is {earnings.confidence} — high change risk")
        if total_debit > spot * 0.03:
            key_risks.append(
                f"Total debit ${total_debit:.2f} is >3% of spot — consider sizing down"
            )

        exit_date = earnings_date - timedelta(days=1)
        if earnings and earnings.report_timing == "BEFORE_OPEN":
            exit_date = earnings_date - timedelta(days=1)
        elif earnings and earnings.report_timing == "AFTER_CLOSE":
            exit_date = earnings_date

        if exit_date < today:
            exit_date = today

        rationale = self.generate_rationale(
            ticker,
            days_to,
            lower,
            upper,
            short_exp,
            long_exp,
            total_debit,
            exit_date,
            scoring_result.overall_score,
        )

        return ConstructedTrade(
            ticker=ticker,
            spot_price=spot,
            earnings_date=earnings_date,
            earnings_confidence=earnings.confidence if earnings else "UNVERIFIED",
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
            strategy_type=self.strategy_type,
        )

    def generate_rationale(
        self,
        ticker: str,
        days_to: int,
        lower: float,
        upper: float,
        short_exp: date,
        long_exp: date,
        total_debit: float,
        exit_date: date,
        score: float,
    ) -> str:
        return (
            f"Double calendar on {ticker} with earnings in {days_to}d. "
            f"Lower calendar at ${lower:.0f}, upper at ${upper:.0f}. "
            f"Short expiry {short_exp}, long expiry {long_exp}. "
            f"Total debit ~${total_debit:.2f}. Exit planned for {exit_date}. "
            f"Score: {score}/100."
        )

    def _select_short_expiry(self, expirations: list[date], earnings_date: date) -> date:
        candidates = [e for e in expirations if e >= earnings_date]
        if candidates:
            return candidates[0]
        return expirations[-1] if expirations else earnings_date

    def _select_long_expiry(self, expirations: list[date], short_expiry: date) -> date:
        min_gap = timedelta(days=14)
        candidates = [e for e in expirations if e >= short_expiry + min_gap]
        if candidates:
            return candidates[0]
        return short_expiry + timedelta(days=28)

    def _snap_strike(
        self, target: float, chain: OptionsChainSnapshot, short_exp: date, long_exp: date
    ) -> float:
        short_strikes = {o.strike for o in chain.options if o.expiration == short_exp}
        long_strikes = {o.strike for o in chain.options if o.expiration == long_exp}
        valid_strikes = sorted(short_strikes.intersection(long_strikes))

        if not valid_strikes:
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
            (1, OptionType.PUT, LegSide.SELL, lower, short_exp),
            (2, OptionType.PUT, LegSide.BUY, lower, long_exp),
            (3, OptionType.CALL, LegSide.SELL, upper, short_exp),
            (4, OptionType.CALL, LegSide.BUY, upper, long_exp),
        ]
        legs = []
        for leg_num, otype, side, strike, exp in configs:
            opt = self._find_option(chain, strike, exp, otype.value)
            legs.append(
                TradeLeg(
                    leg_number=leg_num,
                    option_type=otype,
                    side=side,
                    strike=strike,
                    expiration=exp,
                    option=opt,
                )
            )
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
        for leg in legs:
            if leg.side == LegSide.BUY:
                total += leg.ask or (leg.mid or 0.0)
            else:
                total -= leg.bid or (leg.mid or 0.0)
        return total
