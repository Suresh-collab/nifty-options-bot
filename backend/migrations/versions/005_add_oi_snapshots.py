"""Add oi_snapshots table for OI Buildup forward-test logging

Revision ID: 005
Revises: 004
Create Date: 2026-05-12
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oi_snapshots",
        sa.Column("id",            postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol",        sa.String(20),  nullable=False),
        sa.Column("ts",            sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("spot",          sa.Numeric(18, 4), nullable=False),
        sa.Column("expiry",        sa.String(20),  nullable=True),
        sa.Column("pcr",           sa.Numeric(10, 4), nullable=True),
        sa.Column("total_ce_oi",   sa.BigInteger(), nullable=True),
        sa.Column("total_pe_oi",   sa.BigInteger(), nullable=True),
        sa.Column("atm_ce_oi_chg", sa.BigInteger(), nullable=True),
        sa.Column("atm_pe_oi_chg", sa.BigInteger(), nullable=True),
        sa.Column("regime",        sa.String(40),  nullable=True),
        sa.Column("bias_score",    sa.Numeric(6, 2), nullable=True),
        sa.Column("strikes_json",  postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oi_snapshots_symbol_ts", "oi_snapshots", ["symbol", "ts"])


def downgrade() -> None:
    op.drop_index("ix_oi_snapshots_symbol_ts", table_name="oi_snapshots")
    op.drop_table("oi_snapshots")
