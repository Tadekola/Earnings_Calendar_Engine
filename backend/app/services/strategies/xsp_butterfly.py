"""
XSP Iron Butterfly Strategy.

Scoring tuned for index products (XSP and other cash-settled European-style
index options) where the trading thesis differs fundamentally from equity
butterflies:

  EQUITY butterfly thesis (existing ButterflyStrategy):
    - High IV percentile (>80%)
    - Strong backwardation
    - Short ATM body captures IV crush after earnings

  XSP butterfly thesis (this class):
    - Moderate, stable IV (IV Rank 30-60%)
    - Low realized volatility (market range-bound)
    - Normal contango (no regime stress)
    - Low gap risk (ATR/price small)
    - 7-14 DTE sweet spot for theta vs gamma balance

Hard rejections (auto NO_TRADE):
  - Realized vol > 35% annualized (crisis regime)
  - Term structure slope < -0.20 (severe backwardation)
  - No valid expiry in 3-30 DTE window

Inherits build_trade_structure from ButterflyStrategy (same iron butterfly
structure), but overrides calculate_score and strategy_type.
"""

from __future__ import annotations

from datetime import date

from app.core.enums import RecommendationClass
from app.providers.base import (
    EarningsRecord,
    OptionsChainSnapshot,
    PriceRecord,
    VolatilitySnapshot,
)
from app.services.liquidity import LiquidityCheckResult
from app.services.scoring import ScoreFactor, ScoringResult
from app.services.strategies.butterfly import ButterflyStrategy


class XSPButterflyStrategy(ButterflyStrategy):
    """Iron butterfly scoring tuned for XSP and other index products."""

    @property
    def strategy_type(self) -> str:
        return "XSP_IRON_BUTTERFLY"

    def calculate_score(
        self,
        ticker: str,
        earnings: EarningsRecord | None,
        price: PriceRecord,
        vol: VolatilitySnapshot,
        chain: OptionsChainSnapshot,
        liquidity: LiquidityCheckResult,
    ) -> ScoringResult:
        # ---------- Hard rejections ----------
        rv = vol.realized_vol_20d or 0.0
        if rv > 0.35:
            return self._hard_reject(
                ticker,
                f"Realized vol {rv*100:.1f}% > 35% (crisis regime — butterflies fail)",
            )

        slope = vol.term_structure_slope or 0.0
        if slope < -0.20:
            return self._hard_reject(
                ticker,
                f"Term structure slope {slope:+.3f} < -0.20 "
                "(severe backwardation signals regime stress)",
            )

        # ---------- Factor scoring ----------
        factors: list[ScoreFactor] = []

        # Factor 1: IV Rank (20%) — sweet spot 30-60%
        iv_rank_raw = vol.iv_rank or 0.0
        iv_rank_pct = iv_rank_raw * 100 if iv_rank_raw <= 1.0 else iv_rank_raw
        if 30 <= iv_rank_pct <= 60:
            iv_score = 100.0
        elif 20 <= iv_rank_pct < 30 or 60 < iv_rank_pct <= 70:
            iv_score = 70.0
        elif 10 <= iv_rank_pct < 20 or 70 < iv_rank_pct <= 80:
            iv_score = 40.0
        else:
            iv_score = 10.0
        factors.append(
            ScoreFactor(
                name="IV Rank",
                weight=20.0,
                raw_score=iv_score,
                weighted_score=iv_score * 0.20,
                rationale=(
                    f"IV Rank {iv_rank_pct:.0f}%. Sweet spot 30-60% "
                    "(enough premium without regime risk)."
                ),
            )
        )

        # Factor 2: Realized Vol, 20d annualized (20%) — low is good
        rv_pct = rv * 100
        if rv_pct < 12:
            rv_score = 100.0
        elif rv_pct < 18:
            rv_score = 70.0
        elif rv_pct < 25:
            rv_score = 40.0
        else:
            rv_score = 10.0
        factors.append(
            ScoreFactor(
                name="Realized Volatility (20d)",
                weight=20.0,
                raw_score=rv_score,
                weighted_score=rv_score * 0.20,
                rationale=(
                    f"20d realized vol {rv_pct:.1f}%. "
                    "Low RV = range-bound market = pin more likely."
                ),
            )
        )

        # Factor 3: Term Structure (15%) — mild contango ideal
        # (OPPOSITE of equity butterfly thesis, which prefers backwardation)
        if 0.0 <= slope <= 0.10:
            ts_score = 100.0
        elif 0.10 < slope <= 0.20:
            ts_score = 70.0
        elif -0.05 <= slope < 0.0:
            ts_score = 60.0
        elif slope > 0.20:
            ts_score = 40.0
        else:  # -0.20 <= slope < -0.05
            ts_score = 20.0
        factors.append(
            ScoreFactor(
                name="Term Structure",
                weight=15.0,
                raw_score=ts_score,
                weighted_score=ts_score * 0.15,
                rationale=(
                    f"Slope {slope:+.3f}. Mild contango (0 to +0.10) "
                    "preferred for XSP (no event, stable regime)."
                ),
            )
        )

        # Factor 4: Gap Risk — ATR/Price (15%)
        spot = price.close
        gap_ratio = (vol.atr_14d or 0.0) / spot if spot > 0 else 0.0
        gap_pct = gap_ratio * 100
        if gap_pct < 1.0:
            gap_score = 100.0
        elif gap_pct < 1.5:
            gap_score = 80.0
        elif gap_pct < 2.5:
            gap_score = 50.0
        else:
            gap_score = 15.0
        factors.append(
            ScoreFactor(
                name="Gap Risk (ATR/Price)",
                weight=15.0,
                raw_score=gap_score,
                weighted_score=gap_score * 0.15,
                rationale=(
                    f"ATR/Price {gap_pct:.2f}%. "
                    "Low daily range = lower wing-breach risk."
                ),
            )
        )

        # Factor 5: Liquidity (15%) — pass-through from liquidity engine
        liq_score = getattr(liquidity, "score", 75.0) or 75.0
        factors.append(
            ScoreFactor(
                name="Liquidity",
                weight=15.0,
                raw_score=liq_score,
                weighted_score=liq_score * 0.15,
                rationale=(
                    f"Liquidity score {liq_score:.0f}/100 "
                    "(index-relaxed thresholds applied)."
                ),
            )
        )

        # Factor 6: DTE Fit (15%) — 7-14 sweet spot
        today = date.today()
        expirations = sorted(chain.expirations)
        front_exp = next((e for e in expirations if e > today), None)
        dte = (front_exp - today).days if front_exp else 0

        if front_exp is None or not (3 <= dte <= 30):
            return self._hard_reject(
                ticker,
                f"No valid expiry in 3-30 DTE window (nearest: {dte}d)",
            )

        if 7 <= dte <= 14:
            dte_score = 100.0
        elif 5 <= dte < 7 or 14 < dte <= 21:
            dte_score = 75.0
        elif 3 <= dte < 5 or 21 < dte <= 30:
            dte_score = 50.0
        else:
            dte_score = 20.0
        factors.append(
            ScoreFactor(
                name="DTE Fit",
                weight=15.0,
                raw_score=dte_score,
                weighted_score=dte_score * 0.15,
                rationale=(
                    f"Front expiry {dte}d out. "
                    "Sweet spot 7-14d balances theta vs gamma."
                ),
            )
        )

        # ---------- Aggregate ----------
        overall_score = sum(f.weighted_score for f in factors)
        overall_score = max(0.0, min(100.0, overall_score))

        if overall_score >= self._settings.scoring.RECOMMEND_THRESHOLD:
            classification = RecommendationClass.RECOMMEND
        elif overall_score >= self._settings.scoring.WATCHLIST_THRESHOLD:
            classification = RecommendationClass.WATCHLIST
        else:
            classification = RecommendationClass.NO_TRADE

        rationale = (
            f"XSP Iron Butterfly: IVR={iv_rank_pct:.0f}%, RV={rv_pct:.1f}%, "
            f"Slope={slope:+.3f}, ATR/P={gap_pct:.2f}%, DTE={dte}d. "
            f"Score: {overall_score:.1f}/100."
        )

        # No assignment warnings for XSP (European, cash-settled) — deliberately
        # empty to make the structural advantage visible in the UI.
        return ScoringResult(
            ticker=ticker,
            overall_score=round(overall_score, 1),
            classification=classification,
            factors=factors,
            risk_warnings=[],
            rationale_summary=rationale,
        )

    def _hard_reject(self, ticker: str, reason: str) -> ScoringResult:
        """Produce a NO_TRADE result that bypasses scoring factors."""
        return ScoringResult(
            ticker=ticker,
            overall_score=0.0,
            classification=RecommendationClass.NO_TRADE,
            factors=[],
            risk_warnings=[f"Hard reject: {reason}"],
            rationale_summary=f"XSP butterfly rejected: {reason}",
        )

    def _select_short_expiry(self, expirations: list[date], earnings_date: date) -> date:
        """Override parent behavior: target 7-14 DTE from today, not earnings-based."""
        today = date.today()
        future = sorted(e for e in expirations if e > today)
        if not future:
            return expirations[-1] if expirations else today

        # Prefer 7-14 DTE
        sweet_spot = [e for e in future if 7 <= (e - today).days <= 14]
        if sweet_spot:
            return sweet_spot[0]

        # Next best: 5-21 DTE
        acceptable = [e for e in future if 5 <= (e - today).days <= 21]
        if acceptable:
            return acceptable[0]

        # Fall back to nearest future
        return future[0]
