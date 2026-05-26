"""add sim_orders table

Revision ID: 3b8d5e2a7c19
Revises: 2a4f7c91e035
Create Date: 2026-05-26 00:02:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3b8d5e2a7c19"
down_revision: Union[str, None] = "2a4f7c91e035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sim_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("offset", sa.String(length=8), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("filled_volume", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategy_configs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sim_orders_symbol"), "sim_orders", ["symbol"], unique=False)
    op.create_index(op.f("ix_sim_orders_strategy_id"), "sim_orders", ["strategy_id"], unique=False)
    op.create_index(op.f("ix_sim_orders_user_id"), "sim_orders", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sim_orders_user_id"), table_name="sim_orders")
    op.drop_index(op.f("ix_sim_orders_strategy_id"), table_name="sim_orders")
    op.drop_index(op.f("ix_sim_orders_symbol"), table_name="sim_orders")
    op.drop_table("sim_orders")
