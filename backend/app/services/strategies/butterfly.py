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
from app.services.scoring import ScoreFactor, ScoringResult
from app.services.trade_builder import ConstructedTrade, TradeLeg


class ButterflyStrategy(BaseOptionsStrategy):
    """
    Long Butterfly options strategy.
    Designed for extremely high IV environments to capture massive IV crush.
    Structure: 1 Long Put (Lower Wing), 2 Short Puts (ATM Body), 1 Long Put (Upper Wing)
    or All Calls. Here we will use an All-Put or All-Call structure (Iron Butterfly).
    Structure: 4-leg (2 Long, 2 Short) using the same expiration
    (Front-month/Weekly).
    Let's build an Iron Butterfly (Short ATM Straddle + Long OTM Strangle) for best liquidity.
    """

    def __init__(
        self, settings: Settings, registry, offset: float = 0.0, strategy_id: str = "BUTTERFLY"
    ) -> None:
        super().__init__(settings, registry)
        self._liquidity = LiquidityEngine(settings.liquidity)
        self.offset = offset
        self._strategy_id = strategy_id

    @property
    def strategy_type(self) -> str:
        return self._strategy_id

    def validate_liquidity(
        self,
        price: PriceRecord,
        chain: OptionsChainSnapshot,
        short_exp: date,
        long_exp: date,
    ) -> LiquidityCheckResult:
        # For Butterfly, both short_exp and long_exp are the SAME (Front-month)
        return self._liquidity.evaluate_full(price, chain, short_exp, short_exp)

    def _is_index_product(self, ticker: str) -> bool:
        index_tickers = getattr(self._settings.liquidity, "INDEX_TICKERS", ["XSP"])
        return ticker.upper() in {t.upper() for t in index_tickers}

    def calculate_score(
        self,
        ticker: str,
        earnings: EarningsRecord | None,
        price: PriceRecord,
        vol: VolatilitySnapshot,
        chain: OptionsChainSnapshot,
        liquidity: LiquidityCheckResult,
    ) -> ScoringResult:
        # Custom scoring logic for Butterfly
        factors: list[ScoreFactor] = []
        warnings: list[str] = []

        # Assignment risk: butterflies have short ATM body which is the highest
        # early-exercise risk point on American-style equity options.
        if not self._is_index_product(ticker):
            warnings.append(
                "Early assignment risk: American-style equity options. The short ATM "
                "body is at highest risk of early exercise, especially near expiration "
                "or before ex-dividend dates. Consider XSP (European, cash-settled) for "
                "structurally safer butterflies."
            )
            warnings.append(
                "Ex-dividend gap: scanner does not currently check ex-dividend dates. "
                "Short ITM calls are frequently exercised the day before ex-dividend. "
                "Verify no ex-dividend falls between entry and expiration."
            )

        # 1. IV Percentile (35%): Reward IVP > 80%
        # iv_percentile is 0.0–1.0, convert to percentage
        ivp_raw = vol.iv_percentile or 0.5
        ivp = ivp_raw * 100
        iv_score = 100.0 if ivp > 80 else (60.0 if ivp > 60 else 20.0)
        factors.append(
            ScoreFactor(
                name="Implied Volatility Percentile",
                weight=35.0,
                raw_score=iv_score,
                weighted_score=iv_score * 0.35,
                rationale=(
                    f"IV Percentile is {ivp:.1f}%."
                    " High IVP is required for Iron Butterfly."
                ),
            )
        )

        # 2. Term Structure (25%): Reward Backwardation
        slope = vol.term_structure_slope or 0.0
        slope_score = 100.0 if slope < -0.10 else (70.0 if slope < 0.0 else 30.0)
        factors.append(
            ScoreFactor(
                name="Volatility Term Structure",
                weight=25.0,
                raw_score=slope_score,
                weighted_score=slope_score * 0.25,
                rationale=f"Term structure slope is {slope:.3f}. Backwardation preferred.",
            )
        )

        # 3. Gap Risk (40%): Penalize high ATR/Price ratio
        spot = price.close
        gap_risk = (vol.atr_14d or 0.0) / spot if spot > 0 else 0.0
        gap_score = 100.0 if gap_risk < 0.03 else (60.0 if gap_risk < 0.06 else 10.0)
        factors.append(
            ScoreFactor(
                name="Residual Gap Risk",
                weight=40.0,  # taking the remaining weight
                raw_score=gap_score,
                weighted_score=gap_score * 0.40,
                rationale=(
                    f"ATR to price ratio is {gap_risk*100:.1f}%."
                    " High gap risk penalizes butterflies."
                ),
            )
        )

        # Estimate Risk/Reward for the scan pipeline
        spot = price.close
        days_to = (earnings.earnings_date - date.today()).days if earnings else 0

        front_iv = vol.front_expiry_iv or 0.25
        # Floor at 1 day to avoid zero-width butterfly at DTE=0
        dte_for_move = max(days_to, 1)
        estimated_move = spot * front_iv * (dte_for_move / 365) ** 0.5

        target_spot = spot * (1.0 + self.offset)

        expirations = sorted(chain.expirations)
        front_exp = self._select_short_expiry(
            expirations, earnings.earnings_date if earnings else date.today() + timedelta(days=1)
        )
        body_strike = self._snap_strike(target_spot, chain, front_exp)
        lower_wing = self._snap_strike(body_strike - estimated_move, chain, front_exp)
        upper_wing = self._snap_strike(body_strike + estimated_move, chain, front_exp)

        legs = self._build_legs(ticker, lower_wing, body_strike, upper_wing, front_exp, chain)
        total_debit = sum(leg.debit for leg in legs)
        net_credit = abs(total_debit) if total_debit < 0 else 0.0
        spread_width = body_strike - lower_wing
        max_loss = max(0.0, spread_width - net_credit)
        reward_to_risk = net_credit / max_loss if max_loss > 0 else 0

        # R/R Bonus or Penalty
        if reward_to_risk > 2.0:
            overall_score = sum(f.weighted_score for f in factors) + 10.0
            rationale_bonus = " (Excellent Risk/Reward > 2:1)"
        elif reward_to_risk < 1.0:
            overall_score = sum(f.weighted_score for f in factors) - 20.0
            rationale_bonus = " (Poor Risk/Reward < 1:1)"
        else:
            overall_score = sum(f.weighted_score for f in factors)
            rationale_bonus = ""

        overall_score = max(0.0, min(100.0, overall_score))

        if overall_score >= 80.0:
            classification = RecommendationClass.RECOMMEND
        elif overall_score >= 65.0:
            classification = RecommendationClass.WATCHLIST
        else:
            classification = RecommendationClass.NO_TRADE

        rationale = (
            f"Iron Butterfly Setup: IVP={ivp:.1f}%, Slope={slope:.3f}. "
            f"Estimated Net Credit: ${net_credit:.2f}, Max Risk: ${max_loss:.2f}. "
            f"R/R: {reward_to_risk:.2f}{rationale_bonus}."
        )

        return ScoringResult(
            ticker=ticker,
            overall_score=round(overall_score, 1),
            classification=classification,
            factors=factors,
            risk_warnings=warnings,
            rationale_summary=rationale,
        )

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

        # Step 1: Select Expiry (Butterfly only uses front expiry)
        earnings_date = earnings.earnings_date if earnings else today + timedelta(days=1)
        days_to = (earnings_date - today).days

        expirations = sorted(chain.expirations)
        # Butterfly uses the exact SAME expiration for all 4 legs
        front_exp = override_short_exp or self._select_short_expiry(expirations, earnings_date)

        front_iv = vol.front_expiry_iv or 0.25
        # Floor at 1 day to avoid zero-width butterfly at DTE=0
        dte_for_move = max(days_to, 1)
        estimated_move = spot * front_iv * (dte_for_move / 365) ** 0.5

        # Apply offset to the Spot target
        target_spot = spot * (1.0 + self.offset)

        # Body at Target Spot
        body_strike = self._snap_strike(target_spot, chain, front_exp)

        # Wings symmetrically distributed based on estimated move
        lower_wing = override_lower or self._snap_strike(
            body_strike - estimated_move, chain, front_exp
        )
        upper_wing = override_upper or self._snap_strike(
            body_strike + estimated_move, chain, front_exp
        )

        # Guardrail: if wings collapsed to body strike, force outward
        if lower_wing >= body_strike or upper_wing <= body_strike:
            exp_strikes = sorted(
                {o.strike for o in chain.options if o.expiration == front_exp}
            )
            body_idx = None
            for i, s in enumerate(exp_strikes):
                if s == body_strike:
                    body_idx = i
                    break
            if body_idx is not None:
                if body_idx > 0:
                    lower_wing = exp_strikes[body_idx - 1]
                if body_idx < len(exp_strikes) - 1:
                    upper_wing = exp_strikes[body_idx + 1]

        # Enforce exact symmetry for a standard Iron Butterfly
        lower_diff = body_strike - lower_wing
        upper_diff = upper_wing - body_strike
        if lower_diff != upper_diff:
            # Re-snap the upper wing to match the lower wing width exactly
            target_upper = body_strike + lower_diff
            upper_wing = self._snap_strike(target_upper, chain, front_exp)

        legs = self._build_legs(ticker, lower_wing, body_strike, upper_wing, front_exp, chain)

        total_debit = sum(leg.debit for leg in legs)
        total_debit_pessimistic = self._pessimistic_debit(legs)

        spread_width = body_strike - lower_wing
        net_credit = abs(total_debit) if total_debit < 0 else 0.0
        max_loss = spread_width - net_credit
        max_profit = net_credit

        full_liq = self.validate_liquidity(price, chain, front_exp, front_exp)
        base_score = self.calculate_score(ticker, earnings, price, vol, chain, full_liq)

        # Hard Stop for bad Iron Butterfly Risk/Reward
        if max_loss > 0 and (net_credit / max_loss) < 1.0:
            base_score.overall_score = min(base_score.overall_score, 60.0)
            base_score.classification = RecommendationClass.NO_TRADE

        gap_risk = (vol.atr_14d or 0.0) / spot if spot > 0 else 0.0

        key_risks = [
            "Earnings date may change — verify before entry",
            "Zero residual value if stock breaches wings",
            "High pin risk if stock lands exactly on body strike",
        ]

        # Assignment risk is elevated on American-style equity butterflies
        # (short ATM body). Index products (XSP) are European-style and cash-settled.
        if not self._is_index_product(ticker):
            key_risks.insert(
                0,
                "Early assignment risk: short ATM body on American-style equity "
                "options can be exercised anytime — highest risk near expiration "
                "and before ex-dividend dates. Prefer XSP for structural safety.",
            )
            key_risks.append(
                "Ex-dividend not checked: verify no ex-dividend date falls between "
                "entry and expiration (short ITM calls are routinely exercised the "
                "day before ex-dividend)."
            )

        if earnings and earnings.confidence != "CONFIRMED":
            key_risks.insert(0, f"Earnings date is {earnings.confidence} — high change risk")

        if gap_risk > 0.10:
            key_risks.append(
                f"High Risk: Average true range > 10% "
                f"({gap_risk*100:.1f}%). Highly susceptible to gap-overs."
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
            lower_wing,
            body_strike,
            upper_wing,
            front_exp,
            total_debit,
            exit_date,
            base_score.overall_score,
        )

        return ConstructedTrade(
            ticker=ticker,
            spot_price=spot,
            earnings_date=earnings_date,
            earnings_confidence=earnings.confidence if earnings else "UNVERIFIED",
            entry_date_start=today,
            entry_date_end=today + timedelta(days=2),
            planned_exit_date=exit_date,
            short_expiry=front_exp,
            long_expiry=front_exp,  # Same for butterfly
            lower_strike=lower_wing,
            upper_strike=upper_wing,
            legs=legs,
            total_debit_mid=round(total_debit, 2),
            total_debit_pessimistic=round(total_debit_pessimistic, 2),
            estimated_max_loss=round(max_loss, 2),
            profit_zone_low=round(body_strike - max_profit, 2),
            profit_zone_high=round(body_strike + max_profit, 2),
            classification=base_score.classification,
            overall_score=round(base_score.overall_score, 1),
            rationale_summary=rationale,
            key_risks=key_risks,
            strategy_type=self.strategy_type,
        )

    def generate_rationale(
        self,
        ticker: str,
        days_to: int,
        lower_wing: float,
        body_strike: float,
        upper_wing: float,
        exp: date,
        total_debit: float,
        exit_date: date,
        score: float,
    ) -> str:
        return (
            f"Iron Butterfly on {ticker}. "
            f"Body at ${body_strike:.0f}, Wings at ${lower_wing:.0f}/${upper_wing:.0f}. "
            f"Expiration {exp}. "
            f"Total debit ~${total_debit:.2f}. "
            f"Score: {score:.1f}/100."
        )

    def _select_short_expiry(self, expirations: list[date], earnings_date: date) -> date:
        candidates = [e for e in expirations if e >= earnings_date]
        if candidates:
            return candidates[0]
        return expirations[-1] if expirations else earnings_date

    def _snap_strike(self, target: float, chain: OptionsChainSnapshot, exp: date) -> float:
        valid_strikes = sorted({o.strike for o in chain.options if o.expiration == exp})
        if not valid_strikes:
            return round(target, 0)
        return min(valid_strikes, key=lambda s: abs(s - target))

    def _build_legs(
        self,
        ticker: str,
        lower_wing: float,
        body_strike: float,
        upper_wing: float,
        exp: date,
        chain: OptionsChainSnapshot,
    ) -> list[TradeLeg]:
        # Iron Butterfly: Long Put Wing, Short Put Body, Short Call Body, Long Call Wing
        configs = [
            (1, OptionType.PUT, LegSide.BUY, lower_wing, exp),  # Long Put
            (2, OptionType.PUT, LegSide.SELL, body_strike, exp),  # Short Put
            (3, OptionType.CALL, LegSide.SELL, body_strike, exp),  # Short Call
            (4, OptionType.CALL, LegSide.BUY, upper_wing, exp),  # Long Call
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
            if (
                abs(o.strike - strike) < 0.01
                and o.expiration == exp
                and o.option_type.lower() == otype_lower
            ):
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
