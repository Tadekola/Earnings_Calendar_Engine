from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.core.enums import (
    OperatingMode,
    RecommendationClass,
    RejectionReason,
    ScanStage,
    UniverseSource,
)
from app.core.logging import get_logger
from app.providers.base import PriceRecord, ProviderMeta
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
    layer_id: str | None = None
    account_id: str | None = None


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
        # Populated once during prefilter; reused in _scan_ticker to avoid
        # double-fetching the same /quote for every passing ticker.
        self._quote_cache: dict[str, PriceRecord] = {}

    async def run(
        self,
        tickers: list[str] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ScanRunResult:
        run_id = str(uuid.uuid4())
        started = datetime.now(UTC)
        self._quote_cache.clear()

        if tickers:
            universe = tickers
        elif self._settings.data.UNIVERSE_SOURCE == UniverseSource.SP500:
            universe = await self._build_sp500_universe()
            # Inject non-earnings tickers (like XSP) into SP500 universe
            for t in self._settings.DEFAULT_UNIVERSE:
                if t == "XSP" and t not in universe:
                    universe.append(t)
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
                    await progress_callback(
                        {
                            "type": "ticker_complete",
                            "run_id": run_id,
                            "ticker": ticker,
                            "classification": result.classification.value,
                            "score": result.overall_score,
                            "index": idx + 1,
                            "total": len(universe),
                            "pct": round(((idx + 1) / len(universe)) * 100, 1),
                        }
                    )
                except Exception:
                    pass

        results.sort(key=lambda r: r.overall_score or 0, reverse=True)
        completed = datetime.now(UTC)

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
            logger.warning(
                "sp500_universe_fallback",
                reason="earnings provider is not FMP, using DEFAULT_UNIVERSE",
            )
            return self._settings.DEFAULT_UNIVERSE

        logger.info("sp500_universe_fetch_start")
        sp500_tickers = await earnings_provider.get_sp500_tickers()
        if not sp500_tickers:
            logger.warning(
                "sp500_universe_fallback",
                reason="FMP returned empty S&P 500 list, using DEFAULT_UNIVERSE",
            )
            return self._settings.DEFAULT_UNIVERSE

        min_days = self._settings.earnings_window.MIN_DAYS_TO_EARNINGS
        max_days = self._settings.earnings_window.MAX_DAYS_TO_EARNINGS
        prefiltered = await earnings_provider.get_tickers_with_earnings_in_window(
            sp500_tickers, min_days, max_days
        )

        if not prefiltered:
            logger.warning(
                "sp500_universe_no_earnings",
                reason="No S&P 500 tickers have earnings in window, using full list",
            )
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

        # Bulk-fetch all quotes in one pass (batches of 10) instead of 1 call
        # per ticker. Results are stored in self._quote_cache so _scan_ticker
        # can reuse them without a second round of /quote calls.
        if has_fmp:
            bulk = await price_provider.get_bulk_quotes(tickers)
            for sym, raw in bulk.items():
                try:
                    from datetime import UTC as _UTC
                    from datetime import datetime as _dt
                    from app.providers.base import ProviderMeta, PriceRecord
                    close = float(raw.get("price", raw.get("previousClose", 0)))
                    self._quote_cache[sym] = PriceRecord(
                        ticker=sym,
                        trade_date=date.today(),
                        open=float(raw.get("open", close)),
                        high=float(raw.get("dayHigh", close)),
                        low=float(raw.get("dayLow", close)),
                        close=close,
                        volume=int(raw.get("volume", 0)),
                        avg_dollar_volume=float(raw.get("avgVolume", 0)) * close
                        if raw.get("avgVolume") else None,
                        meta=ProviderMeta(
                            source_name="fmp_price",
                            freshness_timestamp=_dt.now(_UTC),
                            confidence_score=0.9,
                        ),
                    )
                except Exception:
                    pass
            logger.info("prefilter_bulk_quotes_fetched", count=len(self._quote_cache))

        async def _check_ticker(ticker: str) -> str | None:
            t = ticker.upper()
            if has_fmp:
                quote_data = self._quote_cache.get(t)
                if quote_data is None:
                    return None
                if quote_data.close < pf.MIN_STOCK_PRICE:
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
        if earnings is None and ticker.upper() != "XSP":
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.EARNINGS_ELIGIBILITY,
                rejection_reasons=["No earnings date found"],
                rejection_codes=[RejectionReason.NO_CONFIRMED_EARNINGS],
                rationale_summary=f"{ticker}: No upcoming earnings date.",
            )
        days_to = (earnings.earnings_date - date.today()).days if earnings else 0

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

        # Determine if this is an index product with relaxed liquidity rules
        is_index = ticker.upper() in self._settings.liquidity.INDEX_TICKERS

        # Stage 3: Price + Stock Liquidity
        # Prefer the cache populated during the prefilter (avoids re-fetching
        # the same /quote for every ticker that passed the quality gate).
        price = self._quote_cache.get(ticker.upper())
        if price is None:
            price = await self._registry.price.get_current_price(ticker)
        if price is None:
            # Fallback: try Tradier quote (covers index products like XSP)
            price = await self._get_tradier_fallback_price(ticker)
        if price is None:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.OPTIONS_CHAIN_QUALITY,
                rejection_reasons=["No price data available"],
                rejection_codes=[RejectionReason.STALE_DATA],
                rationale_summary=f"{ticker}: No current price data.",
            )

        # Index products have no meaningful stock volume — skip check
        if not is_index:
            stock_liq = self._liquidity_engine.evaluate_stock_liquidity(price)
            if not stock_liq.passed:
                return TickerScanResult(
                    ticker=ticker,
                    classification=RecommendationClass.NO_TRADE,
                    stage_reached=ScanStage.OPTIONS_CHAIN_QUALITY,
                    rejection_reasons=stock_liq.rejection_reasons,
                    rejection_codes=stock_liq.rejection_codes,
                    rationale_summary=(
                        f"{ticker}: Stock liquidity insufficient."
                        f" {'; '.join(stock_liq.rejection_reasons)}"
                    ),
                )

        # Stage 4: Options Chain Quality
        # Only fetch expirations relevant to the double calendar (near earnings)
        all_expirations = await self._registry.options.get_expirations(ticker)
        earnings_date = earnings.earnings_date if earnings else date.today()
        relevant_exps = [
            d for d in all_expirations if date.today() < d <= earnings_date + timedelta(days=60)
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
                rejection_reasons=[
                    "Cannot find suitable front/back expirations for double calendar"
                ],
                rejection_codes=[RejectionReason.POOR_STRIKE_AVAILABILITY],
                rationale_summary=(
                    f"{ticker}: No suitable expiration pair"
                    " for double calendar structure."
                ),
            )

        options_liq = self._liquidity_engine.evaluate_options_liquidity(
            chain, front_exp, back_exp, is_index=is_index,
        )
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
                    rationale_summary=(
                        f"{ticker}: Options liquidity insufficient."
                        f" {'; '.join(options_liq.rejection_reasons[:2])}"
                    ),
                )

        # Stage 5 + 6: Strategy Selection and Scoring
        # The Regime Filter (Phase 4)
        strategy_factory = StrategyFactory(self._settings, self._registry)

        days_to = (earnings.earnings_date - date.today()).days if earnings else 0

        # V4 Layered State Machine Routing
        layer_id = None
        target_strategy_id = None
        account_id = "SHENIDO"  # Default account, this could be customized later

        if ticker.upper() == "XSP":
            target_strategy_id = "XSP_IRON_BUTTERFLY"
            layer_id = "L4"
            account_id = "IBKR_PERSONAL"
        elif days_to >= 7:
            # Phase 1: Pre-Earnings Anticipation (Long Vega)
            target_strategy_id = "DOUBLE_CALENDAR"
            layer_id = "L1"
        elif 0 <= days_to <= 2:
            # Phase 2: Imminent Earnings (Short Vega / IV Crush)
            target_strategy_id = "IRON_BUTTERFLY_ATM"
            layer_id = "L2"
        elif -3 <= days_to < 0:
            # Phase 3: Post-Earnings Drift
            target_strategy_id = "IRON_BUTTERFLY_BULLISH"
            layer_id = "L3"
        else:
            # Not in a valid phase window (e.g., days_to is 3, 4, 5, 6)
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.EARNINGS_ELIGIBILITY,
                rejection_reasons=[f"Days to earnings ({days_to}) not in a valid phase window"],
                rejection_codes=[RejectionReason.EARNINGS_TOO_CLOSE],
                rationale_summary=(
                    f"{ticker}: {days_to} days to earnings does not fit"
                    " Phase 1 (>=7), Phase 2 (0-2), or Phase 3 (-3 to -1)."
                ),
            )

        # Execute scoring specifically for the State Machine target
        strategy = strategy_factory.get_strategy(target_strategy_id)

        # We must re-evaluate liquidity per-strategy (since expirations differ)
        if target_strategy_id == "DOUBLE_CALENDAR":
            strat_front, strat_back = front_exp, back_exp
        else:  # BUTTERFLY
            strat_front, strat_back = front_exp, front_exp

        strat_liq = self._liquidity_engine.evaluate_full(
            price, chain, strat_front, strat_back, is_index=is_index,
        )

        best_result = strategy.calculate_score(
            ticker=ticker,
            earnings=earnings,
            price=price,
            vol=vol,
            chain=chain,
            liquidity=strat_liq,
        )
        best_strategy = target_strategy_id

        # Re-classify based on final score
        if best_result.overall_score >= self._settings.scoring.RECOMMEND_THRESHOLD:
            best_result.classification = RecommendationClass.RECOMMEND
        elif best_result.overall_score >= self._settings.scoring.WATCHLIST_THRESHOLD:
            best_result.classification = RecommendationClass.WATCHLIST
        else:
            best_result.classification = RecommendationClass.NO_TRADE

        # Assignment-risk safeguard: equity butterflies (L2/L3) carry early-exercise
        # risk on the short ATM body (American-style options). Cap them at
        # WATCHLIST so they never surface as RECOMMEND. XSP butterflies are
        # unaffected (European-style, cash-settled). Controlled by
        # settings.scoring.CAP_EQUITY_BUTTERFLIES.
        if (
            getattr(self._settings.scoring, "CAP_EQUITY_BUTTERFLIES", True)
            and best_strategy in ("IRON_BUTTERFLY_ATM", "IRON_BUTTERFLY_BULLISH")
            and not is_index
            and best_result.classification == RecommendationClass.RECOMMEND
        ):
            best_result.classification = RecommendationClass.WATCHLIST
            cap_note = (
                " [Capped to WATCHLIST: equity butterfly has early-assignment risk "
                "on short ATM body. Prefer XSP for RECOMMEND-tier butterflies.]"
            )
            if best_result.rationale_summary:
                best_result.rationale_summary += cap_note
            else:
                best_result.rationale_summary = cap_note.strip()

        logger.info(
            "ticker_scanned",
            ticker=ticker,
            classification=best_result.classification,
            score=best_result.overall_score,
            strategy=best_strategy,
            layer=layer_id,
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
            layer_id=layer_id,
            account_id=account_id,
        )

    async def _check_earnings(self, ticker: str) -> TickerScanResult | None:
        if ticker.upper() == "XSP":
            return None  # XSP doesn't have traditional earnings, let it pass

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

        # Updated Layered State Machine Boundaries
        # We allow up to MAX_DAYS_TO_EARNINGS, and down to -3 days (T+3)
        if days_to > self._settings.earnings_window.MAX_DAYS_TO_EARNINGS:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.EARNINGS_ELIGIBILITY,
                rejection_reasons=[f"Earnings too far: {days_to} days"],
                rejection_codes=[RejectionReason.EARNINGS_TOO_FAR],
                rationale_summary=(
                    f"{ticker}: Earnings in {days_to}d,"
                    f" above max {self._settings.earnings_window.MAX_DAYS_TO_EARNINGS}d."
                ),
            )

        if days_to < -3:
            return TickerScanResult(
                ticker=ticker,
                classification=RecommendationClass.NO_TRADE,
                stage_reached=ScanStage.EARNINGS_ELIGIBILITY,
                rejection_reasons=[f"Earnings passed: {days_to} days"],
                rejection_codes=[RejectionReason.EARNINGS_TOO_CLOSE],
                rationale_summary=f"{ticker}: Earnings passed {abs(days_to)}d ago.",
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
                rationale_summary=(
                    f"{ticker}: Unverified earnings date."
                    " Rejected under strict mode."
                ),
            )

        return None  # passed

    def _select_expirations(self, chain, earnings, days_to: int) -> tuple[date | None, date | None]:
        today = date.today()
        earnings_date = earnings.earnings_date if earnings else today

        available = sorted(chain.expirations)
        if not available:
            return None, None

        # For non-earnings plays (like XSP), just pick the closest expiration and 14 days out
        if not earnings:
            valid = [d for d in available if d > today]
            if valid:
                front = valid[0]
                back_candidates = [
                    d for d in valid if d >= front + timedelta(days=14)
                ]
                back = (
                    back_candidates[0]
                    if back_candidates
                    else (valid[1] if len(valid) > 1 else None)
                )
                return front, back
            return None, None

        # Front expiration: closest expiry ON or AFTER earnings (sell short-dated)
        # This captures the elevated IV that will crush after the event
        front_candidates = [d for d in available if d >= earnings_date]

        # Back expiration: at least 14 days after front expiration (buy longer-dated)
        min_gap = timedelta(days=14)
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

    async def _get_tradier_fallback_price(self, ticker: str) -> PriceRecord | None:
        """Fallback price lookup via Tradier /markets/quotes.
        Covers index products (XSP, etc.) that FMP doesn't support."""
        from app.providers.live.tradier import TradierOptionsProvider

        options_provider = self._registry.options
        if not isinstance(options_provider, TradierOptionsProvider):
            return None

        def _f(v, default: float = 0.0) -> float:
            """Coerce None-or-missing Tradier numeric field to float safely."""
            try:
                return float(v) if v is not None else default
            except (TypeError, ValueError):
                return default

        try:
            data = await options_provider._request(
                "/markets/quotes", {"symbols": ticker.upper()}
            )
            quotes = (data.get("quotes") or {}).get("quote", {})
            if isinstance(quotes, list):
                quotes = quotes[0] if quotes else {}
            # Overnight/pre-market, Tradier returns null for `last` on index
            # products (XSP). Fall back to prevclose/close so scans still score.
            last = (
                _f(quotes.get("last"))
                or _f(quotes.get("close"))
                or _f(quotes.get("prevclose"))
            )
            if last <= 0:
                return None

            return PriceRecord(
                ticker=ticker.upper(),
                trade_date=date.today(),
                open=_f(quotes.get("open"), last),
                high=_f(quotes.get("high"), last),
                low=_f(quotes.get("low"), last),
                close=last,
                volume=int(_f(quotes.get("volume"))),
                avg_dollar_volume=(
                    _f(quotes.get("average_volume")) * last
                    if quotes.get("average_volume")
                    else None
                ),
                meta=ProviderMeta(
                    source_name="tradier_quote_fallback",
                    freshness_timestamp=datetime.now(UTC),
                    confidence_score=0.85,
                ),
            )
        except Exception as e:
            logger.debug("tradier_fallback_price_failed", ticker=ticker, error=str(e))
            return None
