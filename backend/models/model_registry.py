from sqlalchemy import Column, Integer, String, DateTime, Boolean, LargeBinary, JSON
from sqlalchemy.sql import func
from db.base import Base


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(64),  nullable=False)   # 'direction_model' | 'regime_classifier'
    version     = Column(String(32),  nullable=False)   # 'v1', 'v2', …
    symbol      = Column(String(16),  nullable=False)   # 'NIFTY' | 'BANKNIFTY' | 'ALL'
    interval    = Column(String(8),   nullable=False)   # '5m' | '1d'
    trained_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    train_start = Column(String(10),  nullable=False)   # ISO date '2024-01-01'
    train_end   = Column(String(10),  nullable=False)
    metrics     = Column(JSON,        nullable=True)    # {"auc": 0.57, "brier": 0.23, …}
    artifact    = Column(LargeBinary, nullable=False)   # joblib-serialised model bytes
    is_active   = Column(Boolean,     nullable=False, default=False)
