from sqlalchemy import String, Float, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from db.base import Base


class OHLCVCache(Base):
    __tablename__ = "ohlcv_cache"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    interval: Mapped[str] = mapped_column(String(10), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    o: Mapped[float] = mapped_column(Float, nullable=False)
    h: Mapped[float] = mapped_column(Float, nullable=False)
    l: Mapped[float] = mapped_column(Float, nullable=False)
    c: Mapped[float] = mapped_column(Float, nullable=False)
    v: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index("ix_ohlcv_symbol_interval", "symbol", "interval"),
    )
