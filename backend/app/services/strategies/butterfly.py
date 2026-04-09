from __future__ import annotations

from datetime import date, timedelta

from app.core.config import Settings
from app.core.enums import LegSide, OptionType, RecommendationClass
from app.providers.base import (
    EarningsRecord,
    OptionsChainSnapshot,
    OptionRecord,
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
    Wait, the prompt says: "Structure: 4-leg (2 Long, 2 Short) using the same expiration (Front-month/Weekly)."
    Let's build an Iron Butterfly (Short ATM Straddle + Long OTM Strangle) for best liquidity.
    """

    def __init__(self, settings: Settings, registry) -> None:
        super().__init__(settings, registry)
        self._liquidity = LiquidityEngine(settings.liquidity)

    @property
    def strategy_type(self) -> str:
        return "BUTTERFLY"

    def validate_liquidity(
        self,
        price: PriceRecord,
        chain: OptionsChainSnapshot,
        short_exp: date,
        long_exp: date,
    ) -> LiquidityCheckResult:
        # For Butterfly, both short_exp and long_exp are the SAME (Front-month)
        return self._liquidity.evaluate_full(price, chain, short_exp, short_exp)

    def calculate_score(
        self,
        ticker: str,
        earnings: EarningsRecord,
        price: PriceRecord,
        vol: VolatilitySnapshot,
        chain: OptionsChainSnapshot,
        liquidity: LiquidityCheckResult,
    ) -> ScoringResult:
        # Custom scoring logic for Butterfly
        factors: list[ScoreFactor] = []
        warnings: list[str] = []
        
        # 1. IV Percentile (35%): Reward IVP > 80
        ivp = vol.iv_percentile or 0.0
        ivp_score = min(100.0, max(0.0, (ivp - 0.4) * 200)) if ivp > 0.4 else 0.0
        if ivp > 0.8:
            ivp_score = 100.0
            
        factors.append(ScoreFactor(
            name="IV Percentile",
            weight=35.0,
            raw_score=ivp_score,
            weighted_score=ivp_score * 0.35,
            rationale=f"IV Percentile is {ivp*100:.1f}% (>80% is optimal for Butterflies)."
        ))

        # We will need the actual trade to calculate Risk/Reward. 
        # But `calculate_score` doesn't get the trade object. 
        # For now, we will add a placeholder for R/R that gets updated later, or estimate it.
        # Actually, the base class calculates score BEFORE trade build in the current pipeline.
        # Wait, the prompt says "Risk/Reward (25%): Minimum requirement 1:4". We can't know the exact R/R until trade is built!
        # I'll calculate an estimated R/R based on Greeks/Volatility, or we can just build the trade inside `calculate_score` if we really have to.
        
        # 3. Residual Value Risk (Penalize gap risk)
        # Using ATR as a proxy for gap risk
        atr = vol.atr_14d or 0.0
        gap_risk = (atr / price.close) if price.close > 0 else 0.0
        gap_score = 100.0 - min(100.0, gap_risk * 1000) # High gap risk = low score
        
        factors.append(ScoreFactor(
            name="Residual Gap Risk",
            weight=40.0,  # taking the remaining weight
            raw_score=gap_score,
            weighted_score=gap_score * 0.40,
            rationale=f"ATR to price ratio is {gap_risk*100:.1f}%. High gap risk penalizes butterflies."
        ))

        # Estimate Risk/Reward for the scan pipeline
        spot = price.close
        days_to = (earnings.earnings_date - date.today()).days
        front_iv = vol.front_expiry_iv or 0.25
        estimated_move = spot * front_iv * (days_to / 365) ** 0.5
        
        expirations = sorted(chain.expirations)
        front_exp = self._select_short_expiry(expirations, earnings.earnings_date)
        body_strike = self._snap_strike(spot, chain, front_exp)
        lower_wing = self._snap_strike(spot - estimated_move, chain, front_exp)
        upper_wing = self._snap_strike(spot + estimated_move, chain, front_exp)
        
        legs = self._build_legs(ticker, lower_wing, body_strike, upper_wing, front_exp, chain)
        total_debit = sum(l.debit for l in legs)
        net_credit = abs(total_debit) if total_debit < 0 else 0.0
        spread_width = body_strike - lower_wing
        max_loss = max(0.0, spread_width - net_credit)
        reward_to_risk = net_credit / max_loss if max_loss > 0 else 0
        rr_score = min(100.0, (reward_to_risk / 4.0) * 100.0) 

        factors.append(ScoreFactor(
            name="Risk/Reward",
            weight=25.0,
            raw_score=rr_score,
            weighted_score=rr_score * 0.25,
            rationale=f"Estimated Max Loss: ${max_loss:.2f}, Credit: ${net_credit:.2f}. "
                      f"R/R is 1:{reward_to_risk:.1f} (target 1:4)."
        ))

        # Regime Filter Bonus
        ivp = vol.iv_percentile or 0.0
        high_absolute_iv = (ivp > 0.8) # proxy for 52-wk high

        bonus_rationale = ""
        if high_absolute_iv:
            factors.append(ScoreFactor(
                name="Regime Filter",
                weight=10.0,
                raw_score=100.0,
                weighted_score=10.0,
                rationale="High Absolute IV regime detected. +10 bonus for Butterfly."
            ))
            bonus_rationale = " (+10 bonus for High Absolute IV regime)"

        overall_score = min(100.0, sum(f.weighted_score for f in factors))
        classification = RecommendationClass.NO_TRADE
        if overall_score >= self._settings.scoring.RECOMMEND_THRESHOLD:
            classification = RecommendationClass.RECOMMEND
        elif overall_score >= self._settings.scoring.WATCHLIST_THRESHOLD:
            classification = RecommendationClass.WATCHLIST
            
        warnings = []
        if not liquidity.passed:
            warnings.append(f"Liquidity rejected: {'; '.join(liquidity.rejection_reasons)}")
        if gap_risk > 0.10:
            warnings.append(f"High Gap Risk: estimated expected move {gap_risk*100:.1f}% exceeds typical spread width.")

        rationale = f"Butterfly Score: {overall_score:.1f}/100. {bonus_rationale}"
        
        return ScoringResult(
            ticker=ticker,
            overall_score=round(overall_score, 1),
            classification=classification,
            factors=factors,
            risk_warnings=warnings,
            rationale_summary=rationale
        )

    def build_trade_structure(
        self,
        ticker: str,
        earnings: EarningsRecord,
        price: PriceRecord,
        vol: VolatilitySnapshot,
        chain: OptionsChainSnapshot,
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

        expirations = sorted(chain.expirations)
        # Butterfly uses the exact SAME expiration for all 4 legs
        front_exp = override_short_exp or self._select_short_expiry(expirations, earnings.earnings_date)

        front_iv = vol.front_expiry_iv or 0.25
        estimated_move = spot * front_iv * (days_to / 365) ** 0.5

        # Body at ATM
        body_strike = self._snap_strike(spot, chain, front_exp)
        
        # Wings at +/- 1.0 x Expected Move
        lower_wing = override_lower or self._snap_strike(spot - estimated_move, chain, front_exp)
        upper_wing = override_upper or self._snap_strike(spot + estimated_move, chain, front_exp)

        # Iron Butterfly structure:
        # Leg 1: Long Put (Lower Wing)
        # Leg 2: Short Put (ATM Body)
        # Leg 3: Short Call (ATM Body)
        # Leg 4: Long Call (Upper Wing)
        legs = self._build_legs(ticker, lower_wing, body_strike, upper_wing, front_exp, chain)

        total_debit = sum(l.debit for l in legs)
        total_debit_pessimistic = self._pessimistic_debit(legs)

        # Iron Butterfly is a credit spread. total_debit will be negative.
        net_credit = abs(total_debit) if total_debit < 0 else 0.0
        
        # Spread width is the distance between body and wings (assuming symmetric)
        spread_width = body_strike - lower_wing
        
        # Max Loss = Spread Width - Net Credit
        max_loss = max(0.0, spread_width - net_credit)
        
        # Max Profit = Net Credit
        max_profit = net_credit
        
        # Risk/Reward Ratio calculation: we want R:R of 1:4 (risk 1 to make 4)
        # So reward_to_risk = max_profit / max_loss
        reward_to_risk = max_profit / max_loss if max_loss > 0 else 0
        
        # We already have Risk/Reward calculated in calculate_score, so we just run it:
        full_liq = self.validate_liquidity(price, chain, front_exp, front_exp)
        base_score = self.calculate_score(ticker, earnings, price, vol, chain, full_liq)
        
        # Recalculate overall (should match base_score.overall_score)
        if base_score.overall_score >= 80:
            base_score.classification = RecommendationClass.RECOMMEND
        elif base_score.overall_score >= 65:
            base_score.classification = RecommendationClass.WATCHLIST
        else:
            base_score.classification = RecommendationClass.NO_TRADE

        gap_risk = (vol.atr_14d or 0.0) / spot if spot > 0 else 0.0
        
        key_risks = [
            "Earnings date may change — verify before entry",
            "Zero residual value if stock breaches wings",
            "High pin risk if stock lands exactly on body strike",
        ]
        
        if gap_risk > 0.10:
            key_risks.append(f"High Risk: Average true range > 10% ({gap_risk*100:.1f}%). Highly susceptible to gap-overs.")
        
        rationale = self.generate_rationale(ticker, days_to, lower_wing, body_strike, upper_wing, front_exp, total_debit, exit_date, base_score.overall_score)

        return ConstructedTrade(
            ticker=ticker,
            spot_price=spot,
            earnings_date=earnings.earnings_date,
            earnings_confidence=earnings.confidence,
            entry_date_start=today,
            entry_date_end=today + timedelta(days=2),
            planned_exit_date=exit_date,
            short_expiry=front_exp,
            long_expiry=front_exp,  # Same expiry
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
        self, ticker: str, days_to: int, lower_wing: float, body_strike: float, upper_wing: float, 
        exp: date, total_debit: float, exit_date: date, score: float
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
            (1, OptionType.PUT, LegSide.BUY, lower_wing, exp),      # Long Put
            (2, OptionType.PUT, LegSide.SELL, body_strike, exp),    # Short Put
            (3, OptionType.CALL, LegSide.SELL, body_strike, exp),   # Short Call
            (4, OptionType.CALL, LegSide.BUY, upper_wing, exp),     # Long Call
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
