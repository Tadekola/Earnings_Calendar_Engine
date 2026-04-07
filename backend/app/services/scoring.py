from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from app.core.config import EarningsWindowSettings, ScoringSettings
from app.core.enums import RecommendationClass
from app.core.logging import get_logger
from app.providers.base import (
    EarningsRecord,
    OptionsChainSnapshot,
    PriceRecord,
    VolatilitySnapshot,
)
from app.services.liquidity import LiquidityCheckResult

logger = get_logger(__name__)


@dataclass
class ScoreFactor:
    name: str
    weight: float
    raw_score: float  # 0-100
    weighted_score: float  # raw * (weight / total_weight)
    rationale: str = ""


@dataclass
class ScoringResult:
    ticker: str
    overall_score: float
    classification: RecommendationClass
    factors: list[ScoreFactor] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)
    rationale_summary: str = ""
    scoring_version: str = "1.0.0"


class ScoringEngine:
    def __init__(
        self,
        scoring_settings: ScoringSettings,
        earnings_settings: EarningsWindowSettings,
    ) -> None:
        self._scoring = scoring_settings
        self._earnings = earnings_settings
        self._total_weight = (
            scoring_settings.LIQUIDITY_WEIGHT
            + scoring_settings.EARNINGS_TIMING_WEIGHT
            + scoring_settings.VOL_TERM_STRUCTURE_WEIGHT
            + scoring_settings.CONTAINMENT_WEIGHT
            + scoring_settings.PRICING_EFFICIENCY_WEIGHT
            + scoring_settings.EVENT_CLEANLINESS_WEIGHT
            + scoring_settings.HISTORICAL_FIT_WEIGHT
        )

    def score(
        self,
        ticker: str,
        earnings: EarningsRecord,
        price: PriceRecord,
        vol: VolatilitySnapshot,
        chain: OptionsChainSnapshot,
        liquidity: LiquidityCheckResult,
    ) -> ScoringResult:
        factors: list[ScoreFactor] = []
        warnings: list[str] = []
        days_to = (earnings.earnings_date - date.today()).days

        # 1. Liquidity Quality (weight: 25)
        factors.append(self._score_liquidity(liquidity))

        # 2. Earnings Timing (weight: 15)
        factors.append(self._score_earnings_timing(days_to, earnings))

        # 3. Vol Term Structure (weight: 20)
        factors.append(self._score_vol_term_structure(vol))

        # 4. Pre-earnings Containment (weight: 15)
        factors.append(self._score_containment(price, vol, days_to))

        # 5. Pricing Efficiency (weight: 10)
        factors.append(self._score_pricing_efficiency(chain, price))

        # 6. Event Cleanliness (weight: 10)
        factors.append(self._score_event_cleanliness(earnings, vol))

        # 7. Historical Fit (weight: 5)
        factors.append(self._score_historical_fit(vol, price))

        # Compute overall
        overall = sum(f.weighted_score for f in factors)
        overall = max(0.0, min(100.0, overall))

        # Classify
        if overall >= self._scoring.RECOMMEND_THRESHOLD:
            classification = RecommendationClass.RECOMMEND
        elif overall >= self._scoring.WATCHLIST_THRESHOLD:
            classification = RecommendationClass.WATCHLIST
        else:
            classification = RecommendationClass.NO_TRADE

        # Risk warnings
        warnings.extend(self._generate_warnings(earnings, vol, price, days_to, liquidity))

        rationale = self._build_rationale(ticker, overall, classification, factors, days_to, earnings)

        return ScoringResult(
            ticker=ticker,
            overall_score=round(overall, 1),
            classification=classification,
            factors=factors,
            risk_warnings=warnings,
            rationale_summary=rationale,
            scoring_version=self._scoring.SCORING_VERSION,
        )

    def _make_factor(self, name: str, weight: float, raw: float, rationale: str) -> ScoreFactor:
        raw = max(0.0, min(100.0, raw))
        weighted = raw * (weight / self._total_weight)
        return ScoreFactor(
            name=name,
            weight=weight,
            raw_score=round(raw, 1),
            weighted_score=round(weighted, 2),
            rationale=rationale,
        )

    # --- Factor 1: Liquidity Quality ---
    def _score_liquidity(self, liquidity: LiquidityCheckResult) -> ScoreFactor:
        raw = liquidity.score
        rationale = f"Liquidity score {raw:.0f}/100."
        if not liquidity.passed:
            rationale += f" Issues: {'; '.join(liquidity.rejection_reasons[:2])}."
        return self._make_factor("Liquidity Quality", self._scoring.LIQUIDITY_WEIGHT, raw, rationale)

    # --- Factor 2: Earnings Timing ---
    def _score_earnings_timing(self, days_to: int, earnings: EarningsRecord) -> ScoreFactor:
        ideal_center = (self._earnings.MIN_DAYS_TO_EARNINGS + self._earnings.MAX_DAYS_TO_EARNINGS) / 2.0
        ideal_range = (self._earnings.MAX_DAYS_TO_EARNINGS - self._earnings.MIN_DAYS_TO_EARNINGS) / 2.0

        # Bell curve scoring around ideal center
        if ideal_range > 0:
            distance = abs(days_to - ideal_center) / ideal_range
            timing_score = max(0, 100 * (1.0 - distance ** 1.5))
        else:
            timing_score = 50.0

        # Bonus for confirmed dates
        if earnings.confidence == "CONFIRMED":
            timing_score = min(100, timing_score + 10)
        elif earnings.confidence == "UNVERIFIED":
            timing_score *= 0.7

        rationale = (
            f"Earnings in {days_to}d (ideal ~{ideal_center:.0f}d). "
            f"Confidence: {earnings.confidence}."
        )
        return self._make_factor(
            "Earnings Timing", self._scoring.EARNINGS_TIMING_WEIGHT, timing_score, rationale
        )

    # --- Factor 3: Vol Term Structure ---
    def _score_vol_term_structure(self, vol: VolatilitySnapshot) -> ScoreFactor:
        score = 50.0  # neutral baseline
        rationale_parts = []

        # Term structure slope — negative (backwardation) is ideal for calendars
        if vol.term_structure_slope is not None:
            slope = vol.term_structure_slope
            if slope < -0.10:
                score = 95.0
                rationale_parts.append(f"Strong backwardation ({slope:.3f})")
            elif slope < -0.05:
                score = 85.0
                rationale_parts.append(f"Moderate backwardation ({slope:.3f})")
            elif slope < 0:
                score = 70.0
                rationale_parts.append(f"Mild backwardation ({slope:.3f})")
            elif slope < 0.05:
                score = 50.0
                rationale_parts.append(f"Flat term structure ({slope:.3f})")
            else:
                score = 25.0
                rationale_parts.append(f"Contango ({slope:.3f}) — unfavorable for calendars")

        # IV rank context
        if vol.iv_rank is not None:
            if 30 <= vol.iv_rank <= 65:
                score = min(100, score + 10)
                rationale_parts.append(f"IV rank {vol.iv_rank:.0f}% in sweet spot")
            elif vol.iv_rank > 80:
                score = max(0, score - 10)
                rationale_parts.append(f"IV rank {vol.iv_rank:.0f}% elevated — may have limited upside")
            elif vol.iv_rank < 15:
                score = max(0, score - 5)
                rationale_parts.append(f"IV rank {vol.iv_rank:.0f}% low — limited IV expansion potential")

        # Front/back IV ratio
        if vol.front_expiry_iv and vol.back_expiry_iv and vol.back_expiry_iv > 0:
            ratio = vol.front_expiry_iv / vol.back_expiry_iv
            if 1.1 <= ratio <= 1.5:
                score = min(100, score + 8)
                rationale_parts.append(f"Front/back IV ratio {ratio:.2f} ideal")
            elif ratio > 1.5:
                score = min(100, score + 3)
                rationale_parts.append(f"Front/back IV ratio {ratio:.2f} extreme")
            elif ratio < 1.0:
                score = max(0, score - 5)
                rationale_parts.append(f"Front/back IV ratio {ratio:.2f} inverted")

        rationale = "; ".join(rationale_parts) if rationale_parts else "No vol term structure data."
        return self._make_factor(
            "Vol Term Structure", self._scoring.VOL_TERM_STRUCTURE_WEIGHT, score, rationale
        )

    # --- Factor 4: Pre-earnings Containment ---
    def _score_containment(self, price: PriceRecord, vol: VolatilitySnapshot, days_to: int) -> ScoreFactor:
        score = 60.0
        rationale_parts = []

        # Use realized vol to estimate expected pre-earnings range
        rv = vol.realized_vol_20d or vol.realized_vol_10d
        if rv is not None and price.close > 0:
            daily_move_pct = rv / (252 ** 0.5)
            expected_range_pct = daily_move_pct * (days_to ** 0.5)

            if expected_range_pct < 0.03:
                score = 90.0
                rationale_parts.append(f"Tight expected range ({expected_range_pct:.1%})")
            elif expected_range_pct < 0.06:
                score = 75.0
                rationale_parts.append(f"Moderate expected range ({expected_range_pct:.1%})")
            elif expected_range_pct < 0.10:
                score = 55.0
                rationale_parts.append(f"Wide expected range ({expected_range_pct:.1%})")
            else:
                score = 30.0
                rationale_parts.append(f"Very wide expected range ({expected_range_pct:.1%}) — risky")

        # ATR context
        if vol.atr_14d is not None and price.close > 0:
            atr_pct = vol.atr_14d / price.close
            if atr_pct < 0.015:
                score = min(100, score + 10)
                rationale_parts.append(f"Low ATR ({atr_pct:.1%} of price)")
            elif atr_pct > 0.04:
                score = max(0, score - 10)
                rationale_parts.append(f"High ATR ({atr_pct:.1%} of price)")

        rationale = "; ".join(rationale_parts) if rationale_parts else "Limited containment data."
        return self._make_factor(
            "Pre-earnings Containment", self._scoring.CONTAINMENT_WEIGHT, score, rationale
        )

    # --- Factor 5: Pricing Efficiency ---
    def _score_pricing_efficiency(self, chain: OptionsChainSnapshot, price: PriceRecord) -> ScoreFactor:
        if not chain.options:
            return self._make_factor(
                "Pricing Efficiency", self._scoring.PRICING_EFFICIENCY_WEIGHT, 0.0,
                "No options data for pricing evaluation."
            )

        spot = chain.spot_price or price.close
        margin = spot * 0.05
        atm_options = [
            o for o in chain.options
            if abs(o.strike - spot) <= margin and o.bid is not None and o.ask is not None
        ]

        if not atm_options:
            return self._make_factor(
                "Pricing Efficiency", self._scoring.PRICING_EFFICIENCY_WEIGHT, 30.0,
                "No ATM options with valid bid/ask."
            )

        # Evaluate mid-price consistency and spread-to-mid ratio
        spread_to_mids = []
        for o in atm_options:
            mid = (o.bid + o.ask) / 2.0
            if mid > 0:
                spread_to_mids.append((o.ask - o.bid) / mid)

        if not spread_to_mids:
            return self._make_factor(
                "Pricing Efficiency", self._scoring.PRICING_EFFICIENCY_WEIGHT, 30.0,
                "Cannot compute spread-to-mid ratios."
            )

        avg_stm = sum(spread_to_mids) / len(spread_to_mids)
        if avg_stm < 0.03:
            score = 95.0
        elif avg_stm < 0.06:
            score = 80.0
        elif avg_stm < 0.10:
            score = 60.0
        elif avg_stm < 0.15:
            score = 40.0
        else:
            score = 20.0

        rationale = f"Avg ATM spread-to-mid: {avg_stm:.1%} across {len(atm_options)} options."
        return self._make_factor(
            "Pricing Efficiency", self._scoring.PRICING_EFFICIENCY_WEIGHT, score, rationale
        )

    # --- Factor 6: Event Cleanliness ---
    def _score_event_cleanliness(self, earnings: EarningsRecord, vol: VolatilitySnapshot) -> ScoreFactor:
        score = 70.0
        rationale_parts = []

        # Confirmed date = clean event
        if earnings.confidence == "CONFIRMED":
            score = 90.0
            rationale_parts.append("Confirmed earnings date")
        elif earnings.confidence == "ESTIMATED":
            score = 65.0
            rationale_parts.append("Estimated earnings date — some uncertainty")
        else:
            score = 30.0
            rationale_parts.append("Unverified earnings date — high uncertainty")

        # Known report timing is cleaner
        if earnings.report_timing in ("BEFORE_OPEN", "AFTER_CLOSE"):
            score = min(100, score + 8)
            rationale_parts.append(f"Known timing: {earnings.report_timing}")
        else:
            rationale_parts.append("Unknown report timing")

        # Check if IV suggests other catalysts might be priced in
        if vol.iv_rank is not None and vol.iv_rank > 85:
            score = max(0, score - 15)
            rationale_parts.append("Very high IV rank may indicate overlapping catalysts")

        rationale = "; ".join(rationale_parts)
        return self._make_factor(
            "Event Cleanliness", self._scoring.EVENT_CLEANLINESS_WEIGHT, score, rationale
        )

    # --- Factor 7: Historical Fit ---
    def _score_historical_fit(self, vol: VolatilitySnapshot, price: PriceRecord) -> ScoreFactor:
        score = 50.0  # neutral without real historical data
        rationale_parts = []

        # Compare realized vol windows for consistency
        if vol.realized_vol_10d is not None and vol.realized_vol_30d is not None:
            if vol.realized_vol_30d > 0:
                rv_ratio = vol.realized_vol_10d / vol.realized_vol_30d
                if 0.8 <= rv_ratio <= 1.2:
                    score = 75.0
                    rationale_parts.append(f"Stable realized vol (10d/30d ratio: {rv_ratio:.2f})")
                elif rv_ratio > 1.5:
                    score = 35.0
                    rationale_parts.append(f"Spiking vol (10d/30d ratio: {rv_ratio:.2f})")
                elif rv_ratio < 0.6:
                    score = 55.0
                    rationale_parts.append(f"Declining vol (10d/30d ratio: {rv_ratio:.2f})")

        # Placeholder: real historical earnings move data will come in Phase 5
        if not rationale_parts:
            rationale_parts.append("Limited historical data — using baseline score")

        rationale = "; ".join(rationale_parts)
        return self._make_factor(
            "Historical Fit", self._scoring.HISTORICAL_FIT_WEIGHT, score, rationale
        )

    def _generate_warnings(
        self,
        earnings: EarningsRecord,
        vol: VolatilitySnapshot,
        price: PriceRecord,
        days_to: int,
        liquidity: LiquidityCheckResult,
    ) -> list[str]:
        warnings = []

        if earnings.confidence != "CONFIRMED":
            warnings.append(f"Earnings date is {earnings.confidence} — verify before entry.")

        if vol.iv_rank is not None and vol.iv_rank > 80:
            warnings.append(f"IV rank at {vol.iv_rank:.0f}% — elevated. IV expansion may be limited.")

        if days_to <= self._earnings.MIN_DAYS_TO_EARNINGS + 2:
            warnings.append(f"Only {days_to} days to earnings — limited time for theta capture.")

        if not liquidity.passed:
            warnings.append("Liquidity thresholds not fully met — use limit orders and reduce size.")

        if vol.term_structure_slope is not None and vol.term_structure_slope > 0.05:
            warnings.append("Contango term structure — calendars may underperform.")

        warnings.append(
            "This is a decision-support tool only. Options involve risk of total loss. "
            "Exit before earnings announcement."
        )
        return warnings

    def _build_rationale(
        self,
        ticker: str,
        score: float,
        classification: RecommendationClass,
        factors: list[ScoreFactor],
        days_to: int,
        earnings: EarningsRecord,
    ) -> str:
        parts = [f"{ticker}: Score {score:.1f}/100 → {classification.value}."]
        parts.append(f"Earnings in {days_to} days ({earnings.confidence}).")

        top_factors = sorted(factors, key=lambda f: f.weighted_score, reverse=True)[:3]
        strengths = [f.name for f in top_factors if f.raw_score >= 70]
        weaknesses = [f.name for f in factors if f.raw_score < 40]

        if strengths:
            parts.append(f"Strengths: {', '.join(strengths)}.")
        if weaknesses:
            parts.append(f"Weaknesses: {', '.join(weaknesses)}.")

        if classification == RecommendationClass.RECOMMEND:
            parts.append("Favorable pre-earnings double calendar setup.")
        elif classification == RecommendationClass.WATCHLIST:
            parts.append("Moderate setup — monitor for improvement before entry.")
        else:
            parts.append("Does not meet quality thresholds for a double calendar.")

        return " ".join(parts)
