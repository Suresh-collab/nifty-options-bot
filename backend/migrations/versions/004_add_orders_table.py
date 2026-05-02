"""Add broker_orders table for Phase 4 order state machine

Revision ID: 004
Revises: 003
Create Date: 2026-05-02
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "broker_orders",
        sa.Column("id",               postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_order_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol",           sa.String(30),  nullable=False),
        sa.Column("exchange",         sa.String(10),  nullable=False, server_default="NSE"),
        sa.Column("instrument_type",  sa.String(10),  nullable=False, server_default="EQ"),
        sa.Column("transaction_type", sa.String(10),  nullable=False),
        sa.Column("order_type",       sa.String(10),  nullable=False, server_default="MARKET"),
        sa.Column("product",          sa.String(10),  nullable=False, server_default="MIS"),
        sa.Column("qty",              sa.Integer(),   nullable=False),
        sa.Column("price",            sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("trigger_price",    sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("status",           sa.String(20),  nullable=False, server_default="PENDING"),
        sa.Column("broker_order_id",  sa.String(50),  nullable=True),
        sa.Column("broker_response",  postgresql.JSONB(), nullable=True),
        sa.Column("mode",             sa.String(10),  nullable=False, server_default="paper"),
        sa.Column("created_at",       sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at",       sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_broker_orders_client_order_id", "broker_orders", ["client_order_id"]
    )
    op.create_index("ix_broker_orders_status", "broker_orders", ["status"])
    op.create_index("ix_broker_orders_symbol", "broker_orders", ["symbol"])
    op.create_index("ix_broker_orders_mode",   "broker_orders", ["mode"])


def downgrade() -> None:
    op.drop_index("ix_broker_orders_mode",   table_name="broker_orders")
    op.drop_index("ix_broker_orders_symbol", table_name="broker_orders")
    op.drop_index("ix_broker_orders_status", table_name="broker_orders")
    op.drop_constraint("uq_broker_orders_client_order_id", "broker_orders", type_="unique")
    op.drop_table("broker_orders")
