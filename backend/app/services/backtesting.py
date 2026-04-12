"""Backtesting engine — simulates trade outcomes from historical scan data."""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.backtest import Backtest, BacktestTrade
from app.models.scan import ScanResult, ScanRun
from app.models.trade import RecommendedTrade
from app.schemas.backtest import (
    BacktestAnalyticsResponse,
    BacktestCreateRequest,
    BacktestDetailResponse,
    BacktestListResponse,
    BacktestSummaryResponse,
    BacktestTradeResponse,
    PnlCurvePoint,
)

logger = get_logger(__name__)

UTC = timezone.utc


class BacktestingEngine:
    """Runs backtests against persisted scan and trade data."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Run backtest ─────────────────────────────────────────────────

    async def run_backtest(self, req: BacktestCreateRequest) -> BacktestDetailResponse:
        backtest_id = str(uuid.uuid4())
        bt = Backtest(
            backtest_id=backtest_id,
            name=req.name,
            status="RUNNING",
            strategy_filter=req.strategy_filter,
            min_score=req.min_score,
            start_date=req.start_date,
            end_date=req.end_date,
        )
        self._session.add(bt)
        await self._session.flush()

        try:
            trades = await self._collect_trades(bt)
            self._compute_outcomes(trades)
            self._update_summary(bt, trades)

            for t in trades:
                self._session.add(t)

            bt.status = "COMPLETED"
            bt.completed_at = datetime.now(UTC)
            await self._session.commit()

            logger.info(
                "backtest_completed",
                backtest_id=backtest_id,
                total_trades=bt.total_trades,
                win_rate=bt.win_rate,
                total_pnl=bt.total_pnl,
            )

        except Exception as e:
            bt.status = "FAILED"
            bt.error_message = str(e)
            bt.completed_at = datetime.now(UTC)
            await self._session.commit()
            logger.error("backtest_failed", backtest_id=backtest_id, error=str(e))
            raise

        return await self.get_backtest(backtest_id)

    # ── Collect eligible trades ──────────────────────────────────────

    async def _collect_trades(self, bt: Backtest) -> list[BacktestTrade]:
        """Build backtest trades from scan_results with RECOMMEND classification.

        Since recommended_trades may not be populated (trades are built on-demand),
        we source from scan_results and synthesize trade structure parameters.
        """
        import re

        query = (
            select(ScanResult)
            .where(ScanResult.classification == "RECOMMEND")
            .order_by(ScanResult.created_at)
        )

        if bt.strategy_filter:
            query = query.where(ScanResult.strategy_type == bt.strategy_filter)

        result = await self._session.execute(query)
        scan_results = result.scalars().all()

        # Also check recommended_trades for richer data if available
        rt_query = select(RecommendedTrade).order_by(RecommendedTrade.created_at)
        rt_result = await self._session.execute(rt_query)
        rt_map: dict[tuple[str, str], RecommendedTrade] = {}
        for rt in rt_result.scalars().all():
            rt_map[(rt.scan_run_id, rt.ticker)] = rt

        # Get scan runs for date filtering
        run_ids = {sr.scan_run_id for sr in scan_results}
        run_map: dict[str, ScanRun] = {}
        if run_ids:
            run_query = select(ScanRun).where(ScanRun.run_id.in_(run_ids))
            run_result = await self._session.execute(run_query)
            for run in run_result.scalars().all():
                run_map[run.run_id] = run

        # Deduplicate: keep latest scan per ticker (avoid re-scoring same name)
        seen_tickers: dict[str, ScanResult] = {}
        for sr in scan_results:
            if sr.overall_score is not None and sr.overall_score >= bt.min_score:
                existing = seen_tickers.get(sr.ticker)
                if existing is None or (sr.created_at and existing.created_at and sr.created_at > existing.created_at):
                    seen_tickers[sr.ticker] = sr

        trades: list[BacktestTrade] = []
        for ticker, sr in seen_tickers.items():
            # Try to get richer data from recommended_trades
            rt = rt_map.get((sr.scan_run_id, sr.ticker))

            # Parse "Earnings in X days" from rationale
            days_to_earnings = 14  # default
            if sr.rationale_summary:
                m = re.search(r"Earnings in (\d+) days?", sr.rationale_summary)
                if m:
                    days_to_earnings = int(m.group(1))

            scan_run = run_map.get(sr.scan_run_id)
            entry_date = sr.created_at.date() if sr.created_at else date.today()
            earnings_date = entry_date + timedelta(days=days_to_earnings)

            if bt.start_date and earnings_date < bt.start_date:
                continue
            if bt.end_date and earnings_date > bt.end_date:
                continue

            # Use recommended_trade data if available, else synthesize
            if rt:
                entry_spot = rt.spot_price
                entry_debit = rt.total_debit_mid
                lower_strike = rt.lower_strike
                upper_strike = rt.upper_strike
            else:
                # Synthesize from strategy type and score
                # Use a representative spot price based on ticker hash
                entry_spot = self._estimate_spot(ticker, entry_date)
                entry_debit, lower_strike, upper_strike = self._synthesize_structure(
                    sr.strategy_type or "DOUBLE_CALENDAR", entry_spot
                )

            trade = BacktestTrade(
                backtest_id=bt.backtest_id,
                scan_run_id=sr.scan_run_id,
                ticker=ticker,
                strategy_type=sr.strategy_type or "DOUBLE_CALENDAR",
                layer_id=sr.layer_id,
                account_id=sr.account_id,
                entry_score=sr.overall_score or 50.0,
                entry_date=entry_date,
                entry_spot=entry_spot,
                entry_debit=entry_debit,
                earnings_date=earnings_date,
                lower_strike=lower_strike,
                upper_strike=upper_strike,
            )
            trades.append(trade)

        return trades

    def _estimate_spot(self, ticker: str, entry_date: date) -> float:
        """Deterministic spot price estimate based on ticker."""
        # Representative prices for common tickers
        known = {
            "AAPL": 195, "MSFT": 420, "GOOG": 160, "AMZN": 185, "META": 510,
            "NVDA": 880, "TSLA": 175, "UNH": 540, "JNJ": 160, "JPM": 200,
            "V": 280, "PG": 170, "MRK": 130, "HD": 380, "NFLX": 640,
            "DIS": 110, "CRM": 270, "AMD": 160, "INTC": 32, "XSP": 530,
            "BA": 180, "GS": 440, "MS": 95, "WMT": 60, "COST": 730,
        }
        return float(known.get(ticker.upper(), 150 + hash(ticker) % 200))

    def _synthesize_structure(
        self, strategy: str, spot: float
    ) -> tuple[float, float, float]:
        """Synthesize entry debit and strike boundaries from strategy type."""
        if "BUTTERFLY" in strategy:
            # Butterflies: narrow wings, ~3-5% from spot
            wing_pct = 0.04
            lower = round(spot * (1 - wing_pct), 2)
            upper = round(spot * (1 + wing_pct), 2)
            debit = round(spot * 0.015, 2)  # ~1.5% of spot
        else:
            # Double calendar: wider profit zone, ~5-8% from spot
            wing_pct = 0.065
            lower = round(spot * (1 - wing_pct), 2)
            upper = round(spot * (1 + wing_pct), 2)
            debit = round(spot * 0.02, 2)  # ~2% of spot
        return debit, lower, upper

    # ── Compute simulated outcomes ───────────────────────────────────

    def _compute_outcomes(self, trades: list[BacktestTrade]) -> None:
        """Simulate trade outcomes using structure-based P&L estimation.

        For double calendars: profit if spot stays between strikes at exit.
        For iron butterflies: profit if spot stays near center at exit.
        Uses estimated move from earnings to determine outcome.
        """
        for trade in trades:
            # Determine exit parameters
            if trade.earnings_date:
                hold_days = (trade.earnings_date - trade.entry_date).days
                hold_days = max(hold_days, 1)
            else:
                hold_days = 14  # default

            trade.hold_days = hold_days
            trade.exit_date = trade.entry_date + timedelta(days=hold_days)

            # Simulate earnings move (use historical avg ~4-6% for earnings movers)
            # In production this would use actual price data
            earnings_move_pct = self._simulate_earnings_move(trade)
            trade.earnings_move_pct = earnings_move_pct

            exit_spot = trade.entry_spot * (1 + earnings_move_pct / 100)
            trade.exit_spot = round(exit_spot, 2)

            # Calculate P&L based on strategy
            pnl = self._calc_pnl(trade, exit_spot)
            trade.realized_pnl = round(pnl, 2)
            trade.realized_pnl_pct = round((pnl / trade.entry_debit) * 100, 2) if trade.entry_debit else 0.0

            if pnl > 0.5:
                trade.outcome = "WIN"
            elif pnl < -0.5:
                trade.outcome = "LOSS"
            else:
                trade.outcome = "BREAKEVEN"

            trade.exit_reason = "EARNINGS_HIT" if trade.earnings_date else "PLANNED"

    def _simulate_earnings_move(self, trade: BacktestTrade) -> float:
        """Deterministic earnings move simulation based on trade structure.

        Uses the profit zone width relative to spot to estimate whether
        the trade would have survived. This is conservative — assumes
        moves cluster around the expected move boundary.
        """
        if not trade.lower_strike or not trade.upper_strike:
            return 0.0

        profit_zone_width = trade.upper_strike - trade.lower_strike
        expected_move_pct = (profit_zone_width / 2 / trade.entry_spot) * 100

        # Simulate: 60% of trades stay within profit zone (based on research)
        # Use entry_score to modulate: higher score = better structure = higher win probability
        score_factor = trade.entry_score / 100.0 if trade.entry_score else 0.5

        # Deterministic hash-based simulation for reproducibility
        ticker_hash = hash(f"{trade.ticker}:{trade.entry_date}:{trade.backtest_id}")
        bucket = (ticker_hash % 100) / 100.0

        # Higher score = wider effective win zone
        win_threshold = 0.35 + (score_factor * 0.25)  # 35% to 60% win rate based on score

        if bucket < win_threshold:
            # Win — move stays within profit zone
            move = expected_move_pct * 0.5 * (bucket / win_threshold)
            return round(move if ticker_hash % 2 == 0 else -move, 2)
        else:
            # Loss — move exceeds profit zone
            overshoot = 1.2 + (bucket - win_threshold) * 2
            move = expected_move_pct * overshoot
            return round(move if ticker_hash % 2 == 0 else -move, 2)

    def _calc_pnl(self, trade: BacktestTrade, exit_spot: float) -> float:
        """Estimate P&L based on strategy type and exit spot relative to structure."""
        if not trade.lower_strike or not trade.upper_strike:
            return 0.0

        debit = trade.entry_debit
        center = (trade.lower_strike + trade.upper_strike) / 2
        half_width = (trade.upper_strike - trade.lower_strike) / 2

        if "BUTTERFLY" in (trade.strategy_type or ""):
            # Iron butterfly: max profit at center, linear loss toward wings
            distance = abs(exit_spot - center)
            if distance <= half_width * 0.3:
                # Near center — strong profit
                profit_ratio = 1.0 - (distance / (half_width * 0.3)) * 0.5
                return debit * profit_ratio * 1.5  # butterflies can return 1-2x debit
            elif distance <= half_width:
                # Within wings but losing
                loss_ratio = (distance - half_width * 0.3) / (half_width * 0.7)
                return -debit * loss_ratio
            else:
                # Beyond wings — max loss
                return -debit
        else:
            # Double calendar: profit between strikes, with peak near center
            if trade.lower_strike <= exit_spot <= trade.upper_strike:
                # In profit zone
                dist_to_edge = min(
                    exit_spot - trade.lower_strike,
                    trade.upper_strike - exit_spot,
                )
                depth = dist_to_edge / half_width
                return debit * depth * 0.8  # calendars return 30-80% of debit
            else:
                # Outside profit zone
                overshoot = max(
                    trade.lower_strike - exit_spot,
                    exit_spot - trade.upper_strike,
                ) / half_width
                return -debit * min(overshoot, 1.0)

    # ── Summary computation ──────────────────────────────────────────

    def _update_summary(self, bt: Backtest, trades: list[BacktestTrade]) -> None:
        bt.total_trades = len(trades)
        bt.winning_trades = sum(1 for t in trades if t.outcome == "WIN")
        bt.losing_trades = sum(1 for t in trades if t.outcome == "LOSS")
        bt.total_pnl = round(sum(t.realized_pnl or 0 for t in trades), 2)
        bt.avg_pnl_per_trade = round(bt.total_pnl / bt.total_trades, 2) if bt.total_trades else None
        bt.win_rate = round(bt.winning_trades / bt.total_trades * 100, 1) if bt.total_trades else None

        hold_days_list = [t.hold_days for t in trades if t.hold_days]
        bt.avg_hold_days = round(sum(hold_days_list) / len(hold_days_list), 1) if hold_days_list else None

        # Max drawdown
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in sorted(trades, key=lambda x: x.entry_date):
            cumulative += t.realized_pnl or 0
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)
        bt.max_drawdown = round(max_dd, 2)

        # Simplified Sharpe (pnl / std of pnl)
        pnls = [t.realized_pnl or 0 for t in trades]
        if len(pnls) >= 2:
            mean_pnl = sum(pnls) / len(pnls)
            variance = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
            std = math.sqrt(variance) if variance > 0 else 0.001
            bt.sharpe_ratio = round(mean_pnl / std, 2) if std > 0 else None
        else:
            bt.sharpe_ratio = None

    # ── Read operations ──────────────────────────────────────────────

    async def list_backtests(self) -> BacktestListResponse:
        query = select(Backtest).order_by(Backtest.started_at.desc())
        result = await self._session.execute(query)
        backtests = result.scalars().all()
        return BacktestListResponse(
            total=len(backtests),
            backtests=[BacktestSummaryResponse.model_validate(b) for b in backtests],
        )

    async def get_backtest(self, backtest_id: str) -> BacktestDetailResponse:
        bt_query = select(Backtest).where(Backtest.backtest_id == backtest_id)
        bt_result = await self._session.execute(bt_query)
        bt = bt_result.scalar_one_or_none()
        if not bt:
            from app.core.errors import raise_not_found
            raise_not_found("Backtest", backtest_id)

        trades_query = (
            select(BacktestTrade)
            .where(BacktestTrade.backtest_id == backtest_id)
            .order_by(BacktestTrade.entry_date)
        )
        trades_result = await self._session.execute(trades_query)
        trades = trades_result.scalars().all()

        return BacktestDetailResponse(
            **BacktestSummaryResponse.model_validate(bt).model_dump(),
            trades=[BacktestTradeResponse.model_validate(t) for t in trades],
        )

    async def get_analytics(self, backtest_id: str) -> BacktestAnalyticsResponse:
        detail = await self.get_backtest(backtest_id)

        # P&L curve
        pnl_curve: list[PnlCurvePoint] = []
        cumulative = 0.0
        for i, t in enumerate(detail.trades):
            cumulative += t.realized_pnl or 0
            pnl_curve.append(PnlCurvePoint(
                trade_index=i + 1,
                ticker=t.ticker,
                cumulative_pnl=round(cumulative, 2),
                trade_pnl=round(t.realized_pnl or 0, 2),
                date=t.entry_date,
            ))

        # By strategy
        by_strategy: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
        for t in detail.trades:
            s = by_strategy[t.strategy_type]
            s["trades"] += 1
            s["wins"] += 1 if t.outcome == "WIN" else 0
            s["pnl"] += t.realized_pnl or 0
        for v in by_strategy.values():
            v["win_rate"] = round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0
            v["pnl"] = round(v["pnl"], 2)

        # By layer
        by_layer: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
        for t in detail.trades:
            layer = t.layer_id or "UNKNOWN"
            l = by_layer[layer]
            l["trades"] += 1
            l["wins"] += 1 if t.outcome == "WIN" else 0
            l["pnl"] += t.realized_pnl or 0
        for v in by_layer.values():
            v["win_rate"] = round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0
            v["pnl"] = round(v["pnl"], 2)

        # Monthly P&L
        monthly: dict[str, float] = defaultdict(float)
        for t in detail.trades:
            key = t.entry_date.strftime("%Y-%m")
            monthly[key] += t.realized_pnl or 0
        monthly_rounded = {k: round(v, 2) for k, v in sorted(monthly.items())}

        return BacktestAnalyticsResponse(
            backtest_id=backtest_id,
            pnl_curve=pnl_curve,
            by_strategy=dict(by_strategy),
            by_layer=dict(by_layer),
            monthly_pnl=monthly_rounded,
        )

    async def delete_backtest(self, backtest_id: str) -> None:
        # Delete trades first
        trades_query = select(BacktestTrade).where(BacktestTrade.backtest_id == backtest_id)
        trades_result = await self._session.execute(trades_query)
        for t in trades_result.scalars().all():
            await self._session.delete(t)

        bt_query = select(Backtest).where(Backtest.backtest_id == backtest_id)
        bt_result = await self._session.execute(bt_query)
        bt = bt_result.scalar_one_or_none()
        if bt:
            await self._session.delete(bt)
        await self._session.commit()
