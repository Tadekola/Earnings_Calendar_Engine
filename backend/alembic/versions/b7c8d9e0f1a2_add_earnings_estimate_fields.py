"""Add earnings estimate fields

Revision ID: b7c8d9e0f1a2
Revises: 66e86b04c216
Create Date: 2026-06-05 07:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "66e86b04c216"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("earnings_events", sa.Column("eps_estimate", sa.Float(), nullable=True))
    op.add_column("earnings_events", sa.Column("eps_actual", sa.Float(), nullable=True))
    op.add_column("earnings_events", sa.Column("revenue_estimate", sa.Float(), nullable=True))
    op.add_column("earnings_events", sa.Column("revenue_actual", sa.Float(), nullable=True))
    op.add_column(
        "earnings_events",
        sa.Column("estimate_last_updated", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("earnings_events", "estimate_last_updated")
    op.drop_column("earnings_events", "revenue_actual")
    op.drop_column("earnings_events", "revenue_estimate")
    op.drop_column("earnings_events", "eps_actual")
    op.drop_column("earnings_events", "eps_estimate")
