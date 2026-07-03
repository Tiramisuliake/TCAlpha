"""add portfolio_backtest_records

Revision ID: c7e1a9d20b44
Revises: 3afb46c74f15
Create Date: 2026-07-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e1a9d20b44"
down_revision: Union[str, None] = "3afb46c74f15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_backtest_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="backtest"),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_portfolio_backtest_records_user_id",
        "portfolio_backtest_records",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_backtest_records_user_id", table_name="portfolio_backtest_records"
    )
    op.drop_table("portfolio_backtest_records")
