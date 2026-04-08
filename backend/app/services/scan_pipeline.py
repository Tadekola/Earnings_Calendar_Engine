from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.config import Settings
from app.core.enums import OperatingMode, RecommendationClass, RejectionReason, ScanStage, UniverseSource
from app.core.logging import get_logger
from app.providers.registry import ProviderRegistry
from app.services.base_strategy import StrategyFactory
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
    strategy_type: str | None = None


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
    def __init__(self, settings: Settings, registry: ProviderRegistry) -> None:
        self._settings = settings
        self._registry = registry
        self._liquidity_engine = LiquidityEngine(settings.liquidity)
        self._scoring_engine = ScoringEngine(settings.scoring, settings.earnings_window)
        self._strategy = StrategyFactory(settings, registry).get_active_strategies()[0]

    async def run(
        self,
        tickers: list[str] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ScanRunResult:
        run_id = str(uuid.uuid4())
        started = datetime.now(timezone.utc)

        if tickers:
            universe = tickers
        elif self._settings.data.UNIVERSE_SOURCE == UniverseSource.SP500:
            universe = await self._build_sp500_universe()
        else:
            universe = self._settings.DEFAULT_UNIVERSE

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

    async def _build_sp500_universe(self) -> list[str]:
        """Fetch S&P 500 constituents from FMP, then pre-filter to only tickers
        with confirmed earnings within the configured earnings window.
        This avoids running expensive options API calls on all ~500 tickers."""
        from app.providers.live.fmp import FMPEarningsProvider
        earnings_provider = self._registry.earnings
        if not isinstance(earnings_provider, FMPEarningsProvider):
            logger.warning("sp500_universe_fallback", reason="earnings provider is not FMP, using DEFAULT_UNIVERSE")
            return self._settings.DEFAULT_UNIVERSE

        logger.info("sp500_universe_fetch_start")
        sp500_tickers = await earnings_provider.get_sp500_tickers()
        if not sp500_tickers:
            logger.warning("sp500_universe_fallback", reason="FMP returned empty S&P 500 list, using DEFAULT_UNIVERSE")
            return self._settings.DEFAULT_UNIVERSE

        min_days = self._settings.earnings_window.MIN_DAYS_TO_EARNINGS
        max_days = self._settings.earnings_window.MAX_DAYS_TO_EARNINGS
        prefiltered = await earnings_provider.get_tickers_with_earnings_in_window(
            sp500_tickers, min_days, max_days
        )

        if not prefiltered:
            logger.warning("sp500_universe_no_earnings", reason="No S&P 500 tickers have earnings in window, using full list")
            return sp500_tickers

        if self._settings.prefilter.ENABLED:
            prefiltered = await self._apply_quality_prefilter(prefiltered)

        logger.info("sp500_universe_ready", total=len(prefiltered))
        return prefiltered

    async def _apply_quality_prefilter(self, tickers: list[str]) -> list[str]:
        """Drop low-quality tickers before running the full options pipeline.
        Uses Tradier expirations (cheap, 1 call per ticker) to check for weekly options,
        and FMP quote (cheap) to check price + market cap.
        Runs concurrently in batches to stay fast."""
        import asyncio
        from app.providers.live.fmp import FMPPriceProvider

        pf = self._settings.prefilter
        price_provider = self._registry.price
        has_fmp = isinstance(price_provider, FMPPriceProvider)

        logger.info("quality_prefilter_start", candidates=len(tickers))

        async def _check_ticker(ticker: str) -> str | None:
            t = ticker.upper()
            if has_fmp:
                try:
                    quote_data = await price_provider.get_current_price(t)
                    if quote_data is None:
                        return None
                    if quote_data.close < pf.MIN_STOCK_PRICE:
                        return None
                except Exception:
                    return None

            try:
                expirations = await self._registry.options.get_expirations(t)
                if not expirations:
                    return None
                today = date.today()
                future_exps = [e for e in expirations if e > today]

                if len(future_exps) < pf.MIN_EXPIRATION_COUNT:
                    return None

                if pf.REQUIRE_WEEKLY_OPTIONS:
                    has_weeklies = any(0 < (e - today).days <= 14 for e in future_exps)
                    if not has_weeklies:
                        return None
            except Exception:
                return None

            return t

        concurrency = 15
        passed: list[str] = []
        for i in range(0, len(tickers), concurrency):
            batch = tickers[i : i + concurrency]
            results = await asyncio.gather(*[_check_ticker(t) for t in batch])
            passed.extend(r for r in results if r is not None)

        logger.info(
            "quality_prefilter_done",
            before=len(tickers),
            after=len(passed),
            dropped=len(tickers) - len(passed),
        )
        return passed if passed else tickers

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

        # Stage 6: Strategy Selection and Scoring
        # The Regime Filter (Phase 4)
        active_strategies = StrategyFactory(self._settings, self._registry).get_active_strategies()
        best_result = None
        best_strategy = None
        
        # Compute base regime flags
        front_iv = vol.front_expiry_iv or 0.0
        back_iv = vol.back_expiry_iv or 0.0
        ivp = vol.iv_percentile or 0.0
        
        in_backwardation = (front_iv > back_iv * 1.10)  # > 10%
        high_absolute_iv = (ivp > 0.8) # proxy for 52-wk high

        for strategy in active_strategies:
            # We must re-evaluate liquidity per-strategy (since expirations differ)
            if strategy.strategy_type == "DOUBLE_CALENDAR":
                strat_front, strat_back = front_exp, back_exp
            else: # BUTTERFLY
                strat_front, strat_back = front_exp, front_exp
                
            strat_liq = self._liquidity_engine.evaluate_full(price, chain, strat_front, strat_back)
            
            strat_score = strategy.calculate_score(
                ticker=ticker,
                earnings=earnings,
                price=price,
                vol=vol,
                chain=chain,
                liquidity=strat_liq,
            )
            
            # Apply Regime Bonus
            bonus_rationale = ""
            if strategy.strategy_type == "DOUBLE_CALENDAR" and in_backwardation:
                bonus = 10.0
                strat_score.overall_score = min(100.0, strat_score.overall_score + bonus)
                bonus_rationale = " (Bonus applied: +10 for IV Backwardation regime)"
            elif strategy.strategy_type == "BUTTERFLY" and high_absolute_iv:
                bonus = 10.0
                strat_score.overall_score = min(100.0, strat_score.overall_score + bonus)
                bonus_rationale = " (Bonus applied: +10 for High Absolute IV regime)"
                
            if bonus_rationale:
                strat_score.rationale_summary += bonus_rationale

            if best_result is None or strat_score.overall_score > best_result.overall_score:
                best_result = strat_score
                best_strategy = strategy.strategy_type

        # Re-classify based on final boosted score
        if best_result.overall_score >= self._settings.scoring.RECOMMEND_THRESHOLD:
            best_result.classification = RecommendationClass.RECOMMEND
        elif best_result.overall_score >= self._settings.scoring.WATCHLIST_THRESHOLD:
            best_result.classification = RecommendationClass.WATCHLIST
        else:
            best_result.classification = RecommendationClass.NO_TRADE

        logger.info(
            "ticker_scanned",
            ticker=ticker,
            classification=best_result.classification,
            score=best_result.overall_score,
            strategy=best_strategy,
            rationale=best_result.rationale_summary,
        )

        return TickerScanResult(
            ticker=ticker,
            classification=best_result.classification,
            stage_reached=ScanStage.SCORING,
            overall_score=best_result.overall_score,
            scoring_result=best_result,
            rationale_summary=best_result.rationale_summary,
            strategy_type=best_strategy,
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

        # Front expiration: closest expiry ON or AFTER earnings (sell short-dated)
        # This captures the elevated IV that will crush after the event
        front_candidates = [
            d for d in available
            if d >= earnings_date
        ]

        # Back expiration: at least 14 days after front expiration (buy longer-dated)
        min_gap = __import__("datetime").timedelta(days=14)
        back_candidates = []
        if front_candidates:
            front = front_candidates[0]
            back_candidates = [d for d in available if d >= front + min_gap]

        if not front_candidates or not back_candidates:
            # Fallback: if we have at least 2 expirations, use closest pair
            valid = [d for d in available if d > today]
            if len(valid) >= 2:
                return valid[0], valid[1]
            return None, None

        return front_candidates[0], back_candidates[0]
