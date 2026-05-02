import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class BrokerOrder(Base):
    """
    Phase 4 — Broker order state machine persisted in Postgres.
    State flow: PENDING → PLACED → FILLED | REJECTED | CANCELLED
    """
    __tablename__ = "broker_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Caller-generated UUID for idempotency (4.6) — must be unique
    client_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    symbol:           Mapped[str] = mapped_column(String(30),  nullable=False)
    exchange:         Mapped[str] = mapped_column(String(10),  nullable=False, default="NSE")
    instrument_type:  Mapped[str] = mapped_column(String(10),  nullable=False, default="EQ")
    transaction_type: Mapped[str] = mapped_column(String(10),  nullable=False)
    order_type:       Mapped[str] = mapped_column(String(10),  nullable=False, default="MARKET")
    product:          Mapped[str] = mapped_column(String(10),  nullable=False, default="MIS")
    qty:              Mapped[int] = mapped_column(Integer,     nullable=False)
    price:            Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    trigger_price:    Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))

    # State machine field
    status:           Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")

    # Filled by broker on PLACED/FILLED
    broker_order_id:  Mapped[str | None] = mapped_column(String(50), nullable=True)
    broker_response:  Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # paper | live
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="paper")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("client_order_id", name="uq_broker_orders_client_order_id"),
        Index("ix_broker_orders_status",  "status"),
        Index("ix_broker_orders_symbol",  "symbol"),
        Index("ix_broker_orders_mode",    "mode"),
    )
