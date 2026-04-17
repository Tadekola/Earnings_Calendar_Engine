from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.core.config import LiquiditySettings
from app.core.enums import RejectionReason
from app.core.logging import get_logger
from app.providers.base import OptionRecord, OptionsChainSnapshot, PriceRecord

logger = get_logger(__name__)


@dataclass
class LiquidityCheckResult:
    passed: bool
    score: float = 0.0  # 0-100 normalized liquidity quality score
    rejection_reasons: list[str] = field(default_factory=list)
    rejection_codes: list[RejectionReason] = field(default_factory=list)
    details: dict[str, float] = field(default_factory=dict)


class LiquidityEngine:
    def __init__(self, settings: LiquiditySettings) -> None:
        self._settings = settings

    def evaluate_stock_liquidity(self, price: PriceRecord) -> LiquidityCheckResult:
        reasons: list[str] = []
        codes: list[RejectionReason] = []
        details: dict[str, float] = {}

        details["avg_stock_volume"] = float(price.volume)
        if price.volume < self._settings.MIN_AVG_STOCK_VOLUME:
            reasons.append(
                f"Stock volume {price.volume:,}"
                f" below minimum {self._settings.MIN_AVG_STOCK_VOLUME:,}"
            )
            codes.append(RejectionReason.INSUFFICIENT_LIQUIDITY)

        vol_ratio = min(price.volume / self._settings.MIN_AVG_STOCK_VOLUME, 2.0) / 2.0
        score = vol_ratio * 100.0

        return LiquidityCheckResult(
            passed=len(reasons) == 0,
            score=round(score, 1),
            rejection_reasons=reasons,
            rejection_codes=codes,
            details=details,
        )

    def evaluate_options_liquidity(
        self,
        chain: OptionsChainSnapshot,
        front_expiration: date,
        back_expiration: date,
        is_index: bool = False,
    ) -> LiquidityCheckResult:
        reasons: list[str] = []
        codes: list[RejectionReason] = []
        details: dict[str, float] = {}
        sub_scores: list[float] = []

        # Use relaxed thresholds for index products
        min_opt_vol = (
            self._settings.INDEX_MIN_AVG_OPTION_VOLUME if is_index
            else self._settings.MIN_AVG_OPTION_VOLUME
        )
        min_oi = (
            self._settings.INDEX_MIN_OPEN_INTEREST if is_index
            else self._settings.MIN_OPEN_INTEREST
        )
        max_spread = (
            self._settings.INDEX_MAX_BID_ASK_PCT if is_index
            else self._settings.MAX_BID_ASK_PCT
        )

        front_opts = [o for o in chain.options if o.expiration == front_expiration]
        back_opts = [o for o in chain.options if o.expiration == back_expiration]

        if not front_opts or not back_opts:
            return LiquidityCheckResult(
                passed=False,
                score=0.0,
                rejection_reasons=["No options available for required expirations"],
                rejection_codes=[RejectionReason.POOR_OPTIONS_LIQUIDITY],
            )

        # Restrict volume/spread checks to ATM-adjacent strikes (±10% of spot)
        # Deep OTM/ITM strikes have near-zero volume and wide spreads by design
        spot = chain.spot_price
        atm_margin = spot * 0.10

        def _is_atm(o: OptionRecord) -> bool:
            return abs(o.strike - spot) <= atm_margin

        front_atm = [o for o in front_opts if _is_atm(o)] or front_opts
        back_atm = [o for o in back_opts if _is_atm(o)] or back_opts

        # 1. Average option volume
        all_relevant = front_atm + back_atm
        avg_vol = (
            sum(o.volume or 0 for o in all_relevant) / len(all_relevant) if all_relevant else 0
        )
        details["avg_option_volume"] = avg_vol
        if min_opt_vol > 0 and avg_vol < min_opt_vol:
            reasons.append(
                f"Avg option volume {avg_vol:.0f}"
                f" below minimum {min_opt_vol}"
            )
            codes.append(RejectionReason.POOR_OPTIONS_LIQUIDITY)
        if min_opt_vol > 0:
            sub_scores.append(min(avg_vol / min_opt_vol, 2.0) / 2.0)
        else:
            # Volume check disabled (index products); contribute neutral sub-score
            sub_scores.append(1.0)

        # 2. Open interest
        avg_oi = (
            sum(o.open_interest or 0 for o in all_relevant) / len(all_relevant)
            if all_relevant
            else 0
        )  # all_relevant already ATM-filtered
        details["avg_open_interest"] = avg_oi
        if avg_oi < min_oi:
            reasons.append(
                f"Avg open interest {avg_oi:.0f} below minimum {min_oi}"
            )
            codes.append(RejectionReason.POOR_OPTIONS_LIQUIDITY)
        sub_scores.append(min(avg_oi / min_oi, 2.0) / 2.0)

        # 3. Bid-ask spread quality (ATM-filtered)
        spread_scores = self._evaluate_spreads(front_atm + back_atm, details, max_spread)
        if spread_scores["passed"] is False:
            reasons.extend(spread_scores["reasons"])
            codes.append(RejectionReason.WIDE_BID_ASK_SPREADS)
        sub_scores.append(spread_scores["score"])

        # 4. Strike density near ATM
        atm_strike_count = self._count_atm_strikes(chain, front_expiration)
        details["atm_strike_count_front"] = float(atm_strike_count)
        if atm_strike_count < self._settings.MIN_STRIKE_DENSITY:
            reasons.append(
                f"Only {atm_strike_count} strikes near ATM"
                f" for front expiry, need {self._settings.MIN_STRIKE_DENSITY}"
            )
            codes.append(RejectionReason.POOR_STRIKE_AVAILABILITY)
        sub_scores.append(min(atm_strike_count / self._settings.MIN_STRIKE_DENSITY, 2.0) / 2.0)

        # Composite score
        score = (sum(sub_scores) / len(sub_scores)) * 100.0 if sub_scores else 0.0

        return LiquidityCheckResult(
            passed=len(reasons) == 0,
            score=round(score, 1),
            rejection_reasons=reasons,
            rejection_codes=list(set(codes)),
            details=details,
        )

    def _evaluate_spreads(
        self,
        options: list[OptionRecord],
        details: dict[str, float],
        max_spread: float | None = None,
    ) -> dict:
        if not options:
            return {"passed": False, "score": 0.0, "reasons": ["No options to evaluate spreads"]}

        spread_pcts: list[float] = []
        wide_count = 0
        for o in options:
            if o.bid is not None and o.ask is not None and o.ask > 0:
                mid = (o.bid + o.ask) / 2.0
                if mid > 0:
                    spread_pct = (o.ask - o.bid) / mid
                    spread_pcts.append(spread_pct)
                    if spread_pct > self._settings.MAX_BID_ASK_PCT:
                        wide_count += 1

        if not spread_pcts:
            return {"passed": False, "score": 0.0, "reasons": ["No valid bid/ask data"]}

        threshold = max_spread if max_spread is not None else self._settings.MAX_BID_ASK_PCT

        avg_spread = sum(spread_pcts) / len(spread_pcts)
        details["avg_spread_pct"] = round(avg_spread, 4)
        details["wide_spread_count"] = float(wide_count)

        reasons = []
        if avg_spread > threshold:
            reasons.append(
                f"Avg bid-ask spread {avg_spread:.1%}"
                f" exceeds maximum {threshold:.1%}"
            )

        # Score inversely proportional to spread
        spread_score = max(0, 1.0 - (avg_spread / (threshold * 2)))
        return {"passed": len(reasons) == 0, "score": spread_score, "reasons": reasons}

    def _count_atm_strikes(self, chain: OptionsChainSnapshot, expiration: date) -> int:
        spot = chain.spot_price
        margin = spot * 0.05  # 5% around ATM
        exp_opts = [o for o in chain.options if o.expiration == expiration]
        unique_strikes = set()
        for o in exp_opts:
            if abs(o.strike - spot) <= margin:
                unique_strikes.add(o.strike)
        return len(unique_strikes)

    def evaluate_full(
        self,
        price: PriceRecord,
        chain: OptionsChainSnapshot,
        front_expiration: date,
        back_expiration: date,
        is_index: bool = False,
    ) -> LiquidityCheckResult:
        if not is_index:
            stock_result = self.evaluate_stock_liquidity(price)
            if not stock_result.passed:
                return stock_result
        else:
            stock_result = LiquidityCheckResult(passed=True, score=75.0)

        options_result = self.evaluate_options_liquidity(
            chain, front_expiration, back_expiration, is_index=is_index,
        )

        # Blend scores: 30% stock, 70% options
        blended = 0.3 * stock_result.score + 0.7 * options_result.score
        all_details = {**stock_result.details, **options_result.details}

        return LiquidityCheckResult(
            passed=stock_result.passed and options_result.passed,
            score=round(blended, 1),
            rejection_reasons=stock_result.rejection_reasons + options_result.rejection_reasons,
            rejection_codes=list(
                set(stock_result.rejection_codes + options_result.rejection_codes)
            ),
            details=all_details,
        )
