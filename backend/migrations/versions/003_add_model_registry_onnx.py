"""Add model_registry_onnx table for ONNX model storage

Revision ID: 003
Revises: 002
Create Date: 2026-05-01
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_registry_onnx",
        sa.Column("id",             sa.Integer(),               nullable=False, autoincrement=True),
        sa.Column("name",           sa.String(64),              nullable=False),
        sa.Column("symbol",         sa.String(16),              nullable=False),
        sa.Column("interval",       sa.String(8),               nullable=False),
        sa.Column("version",        sa.String(32),              nullable=False),
        sa.Column("onnx_bytes",     sa.LargeBinary(),           nullable=False),
        sa.Column("input_features", sa.Text(),                  nullable=True),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "symbol", "interval", "version",
                            name="uq_model_registry_onnx_name_symbol_interval_version"),
    )
    op.create_index("ix_model_registry_onnx_lookup", "model_registry_onnx",
                    ["name", "symbol", "interval"])


def downgrade() -> None:
    op.drop_index("ix_model_registry_onnx_lookup", table_name="model_registry_onnx")
    op.drop_table("model_registry_onnx")
