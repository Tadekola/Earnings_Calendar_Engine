from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.backtest import (
    BacktestAnalyticsResponse,
    BacktestCreateRequest,
    BacktestDetailResponse,
    BacktestListResponse,
)
from app.services.backtesting import BacktestingEngine

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("", response_model=BacktestDetailResponse)
async def create_backtest(
    req: BacktestCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> BacktestDetailResponse:
    """Run a new backtest against historical trade recommendations."""
    engine = BacktestingEngine(db)
    return await engine.run_backtest(req)


@router.get("", response_model=BacktestListResponse)
async def list_backtests(
    db: AsyncSession = Depends(get_db),
) -> BacktestListResponse:
    """List all backtests."""
    engine = BacktestingEngine(db)
    return await engine.list_backtests()


@router.get("/{backtest_id}", response_model=BacktestDetailResponse)
async def get_backtest(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
) -> BacktestDetailResponse:
    """Get a single backtest with all trade outcomes."""
    engine = BacktestingEngine(db)
    return await engine.get_backtest(backtest_id)


@router.get("/{backtest_id}/analytics", response_model=BacktestAnalyticsResponse)
async def get_backtest_analytics(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
) -> BacktestAnalyticsResponse:
    """Get analytics breakdown for a backtest (P&L curve, by-strategy, by-layer, monthly)."""
    engine = BacktestingEngine(db)
    return await engine.get_analytics(backtest_id)


@router.delete("/{backtest_id}", status_code=204, response_model=None)
async def delete_backtest(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a backtest and all its trade results."""
    engine = BacktestingEngine(db)
    await engine.delete_backtest(backtest_id)
