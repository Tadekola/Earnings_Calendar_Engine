"""add backtest tables

Revision ID: a1b2c3d4e5f6
Revises: 66e86b04c216
Create Date: 2026-04-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "66e86b04c216"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backtests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("backtest_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("strategy_filter", sa.String(50), nullable=True),
        sa.Column("min_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("total_trades", sa.Integer(), server_default="0"),
        sa.Column("winning_trades", sa.Integer(), server_default="0"),
        sa.Column("losing_trades", sa.Integer(), server_default="0"),
        sa.Column("total_pnl", sa.Float(), server_default="0.0"),
        sa.Column("avg_pnl_per_trade", sa.Float(), nullable=True),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("avg_hold_days", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("sharpe_ratio", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("backtest_id"),
    )
    op.create_index("ix_backtests_backtest_id", "backtests", ["backtest_id"])

    op.create_table(
        "backtest_trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("backtest_id", sa.String(36), nullable=False),
        sa.Column("scan_run_id", sa.String(36), nullable=True),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("strategy_type", sa.String(50), nullable=False),
        sa.Column("layer_id", sa.String(10), nullable=True),
        sa.Column("account_id", sa.String(50), nullable=True),
        sa.Column("entry_score", sa.Float(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_spot", sa.Float(), nullable=False),
        sa.Column("entry_debit", sa.Float(), nullable=False),
        sa.Column("entry_iv", sa.Float(), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("exit_spot", sa.Float(), nullable=True),
        sa.Column("exit_credit", sa.Float(), nullable=True),
        sa.Column("exit_iv", sa.Float(), nullable=True),
        sa.Column("exit_reason", sa.String(50), nullable=True),
        sa.Column("earnings_date", sa.Date(), nullable=True),
        sa.Column("earnings_move_pct", sa.Float(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("realized_pnl_pct", sa.Float(), nullable=True),
        sa.Column("hold_days", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(20), nullable=True),
        sa.Column("lower_strike", sa.Float(), nullable=True),
        sa.Column("upper_strike", sa.Float(), nullable=True),
        sa.Column("short_expiry", sa.Date(), nullable=True),
        sa.Column("long_expiry", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_trades_backtest_id", "backtest_trades", ["backtest_id"])
    op.create_index("ix_backtest_trades_ticker", "backtest_trades", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_backtest_trades_ticker", "backtest_trades")
    op.drop_index("ix_backtest_trades_backtest_id", "backtest_trades")
    op.drop_table("backtest_trades")
    op.drop_index("ix_backtests_backtest_id", "backtests")
    op.drop_table("backtests")
