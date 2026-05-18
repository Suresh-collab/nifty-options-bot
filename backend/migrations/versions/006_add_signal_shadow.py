"""Add signal_shadow table — records both current-rule and tuned-rule signals
side-by-side for live comparison (Phase 2 validation before promoting the tuned
weights into the live signal_engine).

Revision ID: 006
Revises: 005
Create Date: 2026-05-18
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signal_shadow",
        sa.Column("id",            postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("ts",            sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("symbol",        sa.String(20),  nullable=False),
        sa.Column("interval",      sa.String(10),  nullable=False),
        sa.Column("spot",          sa.Numeric(18, 4), nullable=False),
        sa.Column("current_signal", sa.String(10), nullable=False),  # BUY_CE / BUY_PE / AVOID
        sa.Column("tuned_signal",   sa.String(10), nullable=False),
        sa.Column("agree",          sa.Boolean(),  nullable=False),
        sa.Column("current_score",  sa.Numeric(6, 2), nullable=True),
        sa.Column("tuned_score",    sa.Numeric(6, 2), nullable=True),
        sa.Column("rsi",            sa.Numeric(6, 2), nullable=True),
        sa.Column("macd_hist",      sa.Numeric(10, 4), nullable=True),
        sa.Column("st_dir",         sa.SmallInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signal_shadow_symbol_ts", "signal_shadow", ["symbol", "ts"])


def downgrade() -> None:
    op.drop_index("ix_signal_shadow_symbol_ts", table_name="signal_shadow")
    op.drop_table("signal_shadow")
