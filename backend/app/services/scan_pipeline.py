from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.config import Settings
from app.core.enums import OperatingMode, RecommendationClass, RejectionReason, ScanStage
from app.core.logging import get_logger
from app.providers.registry import ProviderRegistry
from app.services.liquidity import LiquidityEngine
from app.services.scoring import ScoringEngine, ScoringResult

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

logger = get_logger(__name__)


@dataclass
class TickerScanResult:
    ticker: str
    classification: RecommendationClass
    stage_reached: ScanStage
    overall_score: float | None = None
    scoring_result: ScoringResult | None = None
    rejection_reasons: list[str] = field(default_factory=list)
    rejection_codes: list[RejectionReason] = field(default_factory=list)
    rationale_summary: str = ""
    processing_time_ms: int = 0


@dataclass
class ScanRunResult:
    run_id: str
    status: str
    total_scanned: int
    total_recommended: int
    total_watchlist: int
    total_rejected: int
    operating_mode: str
    scoring_version: str
    started_at: datetime
    completed_at: datetime
    results: list[TickerScanResult] = field(default_factory=list)


class ScanPipeline:
    def __init__(
        self,
        settings: Settings,
        registry: ProviderRegistry,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._liquidity_engine = LiquidityEngine(settings.liquidity)
        self._scoring_engine = ScoringEngine(settings.scoring, settings.earnings_window)

    async def run(
        self,
        tickers: list[str] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ScanRunResult:
        run_id = str(uuid.uuid4())
        started = datetime.now(timezone.utc)
        universe = tickers or self._settings.DEFAULT_UNIVERSE

        logger.info(
            "scan_started",
            run_id=run_id,
            universe_size=len(universe),
            operating_mode=self._settings.OPERATING_MODE.value,
        )

        results: list[TickerScanResult] = []
        recommended = 0
        watchlist = 0
        rejected = 0

        for idx, ticker in enumerate(universe):
            start_ns = time.monotonic_ns()
            result = await self._scan_ticker(ticker)
            result.processing_time_ms = int((time.monotonic_ns() - start_ns) / 1_000_000)
            results.append(result)

            if result.classification == RecommendationClass.RECOMMEND:
                recommended += 1
            elif result.classification == RecommendationClass.WATCHLIST:
                watchlist += 1
            else:
                rejected += 1

            if progress_callback:
                try:
                    await progress_callback({
                        "type": "ticker_complete",
                        "run_id": run_id,
                        "ticker": ticker,
                        "classification": result.classification.value,
                        "score": result.overall_score,
                        "index": idx + 1,
                        "total": len(universe),
                        "pct": round(((idx + 1) / len(universe)) * 100, 1),
                    })
                except Exception:
                    pass

        results.sort(key=lambda r: r.overall_score or 0, reverse=True)
        completed = datetime.now(timezone.utc)

        logger.info(
            "scan_completed",
            run_id=run_id,
            total=len(universe),
            recommended=recommended,
            watchlist=watchlist,
            rejected=rejected,
            duration_ms=int((completed - started).total_seconds() * 1000),
        )

        return ScanRunResult(
            run_id=run_id,
            status="COMPLETED",
            total_scanned=len(universe),
            total_recommended=recommended,
            total_watchlist=watchlist,
            total_rejected=rejected,
            operating_mode=self._settings.OPERATING_MODE.value,
            scoring_version=self._settings.scoring.SCORING_VERSION,
            started_at=started,
            completed_at=completed,
            results=results,
        )

    async def _scan_ticker(self, ticker: str) -> TickerScanResult:
        # Stage 1: Earnings Eligibility
        result = await self._check_earnings(ticker)
        if result is not None:
            return result

        earnings = await self._registry.earnings.get_earnings_date(ticker)
        days_to = (earnings.earnings_date - date.today()).days

        # Stage 2: Volatility Suitability
        vol = await self._registry.volatility.get_volatility_metrics(ticker)
        if vol.meta.confidence_score == 0.0:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.VOLATILITY_SUITABILITY,
                rejection_reasons=["No volatility data available"],
                rejection_codes=[RejectionReason.STALE_DATA],
                rationale_summary=f"{ticker}: No volatility data. Cannot assess suitability.",
            )

        # Stage 3: Price + Stock Liquidity
        price = await self._registry.price.get_current_price(ticker)
        if price is None:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.OPTIONS_CHAIN_QUALITY,
                rejection_reasons=["No price data available"],
                rejection_codes=[RejectionReason.STALE_DATA],
                rationale_summary=f"{ticker}: No current price data.",
            )

        stock_liq = self._liquidity_engine.evaluate_stock_liquidity(price)
        if not stock_liq.passed:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.OPTIONS_CHAIN_QUALITY,
                rejection_reasons=stock_liq.rejection_reasons,
                rejection_codes=stock_liq.rejection_codes,
                rationale_summary=f"{ticker}: Stock liquidity insufficient. {'; '.join(stock_liq.rejection_reasons)}",
            )

        # Stage 4: Options Chain Quality
        # Only fetch expirations relevant to the double calendar (near earnings)
        all_expirations = await self._registry.options.get_expirations(ticker)
        earnings_date = earnings.earnings_date
        relevant_exps = [
            d for d in all_expirations
            if date.today() < d <= earnings_date + timedelta(days=60)
        ]
        chain = await self._registry.options.get_options_chain(ticker, relevant_exps or None)
        if not chain.options:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.OPTIONS_CHAIN_QUALITY,
                rejection_reasons=["No options chain data"],
                rejection_codes=[RejectionReason.POOR_OPTIONS_LIQUIDITY],
                rationale_summary=f"{ticker}: Empty options chain.",
            )

        # Select front and back expirations for the double calendar
        front_exp, back_exp = self._select_expirations(chain, earnings, days_to)
        if front_exp is None or back_exp is None:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.OPTIONS_CHAIN_QUALITY,
                rejection_reasons=["Cannot find suitable front/back expirations for double calendar"],
                rejection_codes=[RejectionReason.POOR_STRIKE_AVAILABILITY],
                rationale_summary=f"{ticker}: No suitable expiration pair for double calendar structure.",
            )

        options_liq = self._liquidity_engine.evaluate_options_liquidity(chain, front_exp, back_exp)
        if not options_liq.passed:
            # In graceful mode, allow watchlist even with marginal liquidity
            if self._settings.OPERATING_MODE == OperatingMode.GRACEFUL and options_liq.score >= 40:
                logger.info("graceful_liquidity_pass", ticker=ticker, score=options_liq.score)
            else:
                return TickerScanResult(
                    ticker=ticker,
                    classification=RecommendationClass.NO_TRADE,
                    stage_reached=ScanStage.OPTIONS_CHAIN_QUALITY,
                    rejection_reasons=options_liq.rejection_reasons,
                    rejection_codes=options_liq.rejection_codes,
                    rationale_summary=f"{ticker}: Options liquidity insufficient. {'; '.join(options_liq.rejection_reasons[:2])}",
                )

        # Stage 5: Full liquidity composite
        full_liq = self._liquidity_engine.evaluate_full(price, chain, front_exp, back_exp)

        # Stage 6: Scoring
        scoring_result = self._scoring_engine.score(
            ticker=ticker,
            earnings=earnings,
            price=price,
            vol=vol,
            chain=chain,
            liquidity=full_liq,
        )

        return TickerScanResult(
            ticker=ticker,
            classification=scoring_result.classification,
            stage_reached=ScanStage.SCORING,
            overall_score=scoring_result.overall_score,
            scoring_result=scoring_result,
            rationale_summary=scoring_result.rationale_summary,
        )

    async def _check_earnings(self, ticker: str) -> TickerScanResult | None:
        earnings = await self._registry.earnings.get_earnings_date(ticker)

        if earnings is None:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.EARNINGS_ELIGIBILITY,
                rejection_reasons=["No earnings date found"],
                rejection_codes=[RejectionReason.NO_CONFIRMED_EARNINGS],
                rationale_summary=f"{ticker}: No upcoming earnings date.",
            )

        days_to = (earnings.earnings_date - date.today()).days

        if days_to < self._settings.earnings_window.MIN_DAYS_TO_EARNINGS:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.EARNINGS_ELIGIBILITY,
                rejection_reasons=[f"Earnings too close: {days_to} days"],
                rejection_codes=[RejectionReason.EARNINGS_TOO_CLOSE],
                rationale_summary=f"{ticker}: Earnings in {days_to}d, below min {self._settings.earnings_window.MIN_DAYS_TO_EARNINGS}d.",
            )

        if days_to > self._settings.earnings_window.MAX_DAYS_TO_EARNINGS:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.EARNINGS_ELIGIBILITY,
                rejection_reasons=[f"Earnings too far: {days_to} days"],
                rejection_codes=[RejectionReason.EARNINGS_TOO_FAR],
                rationale_summary=f"{ticker}: Earnings in {days_to}d, above max {self._settings.earnings_window.MAX_DAYS_TO_EARNINGS}d.",
            )

        if (
            self._settings.earnings_window.REQUIRE_CONFIRMED_DATE
            and earnings.confidence == "UNVERIFIED"
            and self._settings.OPERATING_MODE == OperatingMode.STRICT
        ):
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.EARNINGS_ELIGIBILITY,
                rejection_reasons=["Unverified earnings date in strict mode"],
                rejection_codes=[RejectionReason.NO_CONFIRMED_EARNINGS],
                rationale_summary=f"{ticker}: Unverified earnings date. Rejected under strict mode.",
            )

        return None  # passed

    def _select_expirations(
        self, chain, earnings, days_to: int
    ) -> tuple[date | None, date | None]:
        today = date.today()
        earnings_date = earnings.earnings_date
        exit_date = earnings_date  # simplified: exit day before

        available = sorted(chain.expirations)
        if not available:
            return None, None

        # Front expiration: closest expiry BEFORE earnings (sell short-dated)
        # Should expire around or just before earnings for max theta
        front_candidates = [
            d for d in available
            if today < d <= earnings_date and (d - today).days >= 3
        ]

        # Back expiration: first expiry AFTER earnings (buy longer-dated)
        back_candidates = [
            d for d in available
            if d > earnings_date
        ]

        if not front_candidates or not back_candidates:
            # Fallback: if we have at least 2 expirations, use closest pair
            valid = [d for d in available if d > today]
            if len(valid) >= 2:
                return valid[0], valid[1]
            return None, None

        # Choose the front expiry closest to earnings
        front = max(front_candidates)
        # Choose the back expiry closest to earnings (but after)
        back = min(back_candidates)

        return front, back
