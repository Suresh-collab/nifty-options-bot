import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # BUY_CE | BUY_PE | AVOID
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_signals_ts", "ts"),
        Index("ix_signals_symbol", "symbol"),
    )
