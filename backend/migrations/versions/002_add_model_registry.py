"""Add model_registry table for Phase 2 ML

Revision ID: 002
Revises: 001
Create Date: 2026-05-01
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_registry",
        sa.Column("id",          sa.Integer(),                   nullable=False, autoincrement=True),
        sa.Column("name",        sa.String(64),                  nullable=False),
        sa.Column("version",     sa.String(32),                  nullable=False),
        sa.Column("symbol",      sa.String(16),                  nullable=False),
        sa.Column("interval",    sa.String(8),                   nullable=False),
        sa.Column("trained_at",  sa.DateTime(timezone=True),     server_default=sa.text("now()"), nullable=False),
        sa.Column("train_start", sa.String(10),                  nullable=False),
        sa.Column("train_end",   sa.String(10),                  nullable=False),
        sa.Column("metrics",     sa.JSON(),                      nullable=True),
        sa.Column("artifact",    sa.LargeBinary(),               nullable=False),
        sa.Column("is_active",   sa.Boolean(),                   nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "symbol", "interval", "version",
                            name="uq_model_registry_name_symbol_interval_version"),
    )
    op.create_index("ix_model_registry_active", "model_registry",
                    ["name", "symbol", "interval", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_model_registry_active", table_name="model_registry")
    op.drop_table("model_registry")
