"""add symbols table

Revision ID: 106c88758ee1
Revises:
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "106c88758ee1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "symbols",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=10), nullable=False),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("exchange", sa.String(length=4), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("industry", sa.String(length=64), nullable=True),
        sa.Column("list_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol"),
    )
    op.create_index(op.f("ix_symbols_code"), "symbols", ["code"], unique=False)
    op.create_index(op.f("ix_symbols_is_active"), "symbols", ["is_active"], unique=False)
    op.create_index(op.f("ix_symbols_symbol"), "symbols", ["symbol"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_symbols_symbol"), table_name="symbols")
    op.drop_index(op.f("ix_symbols_is_active"), table_name="symbols")
    op.drop_index(op.f("ix_symbols_code"), table_name="symbols")
    op.drop_table("symbols")
