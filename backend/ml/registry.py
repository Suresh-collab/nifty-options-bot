"""
Model registry — save and load trained models to/from Neon (model_registry table).

Models are serialised with joblib and stored as BYTEA in Postgres.
A module-level LRU cache avoids redundant DB round-trips during inference
(one load per process per (name, symbol, interval) combination).
"""

import io
import logging
from functools import lru_cache
from typing import Any, Optional

import joblib
from sqlalchemy import text

from db.base import get_session_factory

logger = logging.getLogger(__name__)

# In-process cache: key → (version, model_object)
_model_cache: dict[str, tuple[str, Any]] = {}


async def save_model(
    name: str,
    version: str,
    symbol: str,
    interval: str,
    model_obj: Any,
    train_start: str,
    train_end: str,
    metrics: dict,
    set_active: bool = True,
) -> None:
    """
    Serialise `model_obj` with joblib and upsert into model_registry.
    If `set_active=True`, marks all other rows with the same
    (name, symbol, interval) as inactive and this one as active.
    """
    buf = io.BytesIO()
    joblib.dump(model_obj, buf)
    artifact_bytes = buf.getvalue()

    factory = get_session_factory()
    async with factory() as session:
        if set_active:
            await session.execute(
                text(
                    "UPDATE model_registry SET is_active = false "
                    "WHERE name = :name AND symbol = :symbol AND interval = :interval"
                ),
                {"name": name, "symbol": symbol, "interval": interval},
            )

        await session.execute(
            text(
                "INSERT INTO model_registry "
                "  (name, version, symbol, interval, train_start, train_end, metrics, artifact, is_active) "
                "VALUES "
                "  (:name, :version, :symbol, :interval, :train_start, :train_end, "
                "   CAST(:metrics AS jsonb), :artifact, :is_active) "
                "ON CONFLICT (name, symbol, interval, version) DO UPDATE SET "
                "  artifact    = EXCLUDED.artifact, "
                "  metrics     = EXCLUDED.metrics, "
                "  trained_at  = now(), "
                "  is_active   = EXCLUDED.is_active"
            ),
            {
                "name":        name,
                "version":     version,
                "symbol":      symbol,
                "interval":    interval,
                "train_start": train_start,
                "train_end":   train_end,
                "metrics":     _json_str(metrics),
                "artifact":    artifact_bytes,
                "is_active":   set_active,
            },
        )
        await session.commit()

    # Invalidate cache
    cache_key = _cache_key(name, symbol, interval)
    _model_cache.pop(cache_key, None)
    logger.info("Saved model %s/%s/%s v%s to Neon (%d bytes)",
                name, symbol, interval, version, len(artifact_bytes))


async def load_model(
    name: str,
    symbol: str,
    interval: str,
    version: Optional[str] = None,
    use_cache: bool = True,
) -> Optional[Any]:
    """
    Load and deserialise a model from Neon.
    If `version` is None, loads the currently active model.
    Returns None if no matching model is found.
    """
    cache_key = _cache_key(name, symbol, interval, version)

    if use_cache and cache_key in _model_cache:
        cached_ver, obj = _model_cache[cache_key]
        logger.debug("Model cache hit: %s", cache_key)
        return obj

    factory = get_session_factory()
    async with factory() as session:
        if version is None:
            row = await session.execute(
                text(
                    "SELECT version, artifact FROM model_registry "
                    "WHERE name = :name AND symbol = :symbol AND interval = :interval "
                    "  AND is_active = true "
                    "ORDER BY trained_at DESC LIMIT 1"
                ),
                {"name": name, "symbol": symbol, "interval": interval},
            )
        else:
            row = await session.execute(
                text(
                    "SELECT version, artifact FROM model_registry "
                    "WHERE name = :name AND symbol = :symbol "
                    "  AND interval = :interval AND version = :version "
                    "LIMIT 1"
                ),
                {"name": name, "symbol": symbol, "interval": interval, "version": version},
            )
        result = row.fetchone()

    if result is None:
        logger.warning("No model found for %s/%s/%s v=%s", name, symbol, interval, version)
        return None

    loaded_version, artifact_bytes = result
    model_obj = joblib.load(io.BytesIO(bytes(artifact_bytes)))
    _model_cache[cache_key] = (loaded_version, model_obj)
    logger.info("Loaded model %s/%s/%s v%s from Neon", name, symbol, interval, loaded_version)
    return model_obj


async def list_models(name: Optional[str] = None) -> list[dict]:
    """Return metadata rows from model_registry (no artifact bytes)."""
    factory = get_session_factory()
    async with factory() as session:
        where = "WHERE name = :name" if name else ""
        rows = await session.execute(
            text(
                f"SELECT id, name, version, symbol, interval, trained_at, "
                f"       train_start, train_end, metrics, is_active "
                f"FROM model_registry {where} ORDER BY trained_at DESC"
            ),
            {"name": name} if name else {},
        )
        return [dict(r._mapping) for r in rows.fetchall()]


def clear_cache() -> None:
    """Clear the in-process model cache (useful in tests)."""
    _model_cache.clear()


def _cache_key(name: str, symbol: str, interval: str, version: Optional[str] = None) -> str:
    return f"{name}::{symbol}::{interval}::{version or 'active'}"


def _json_str(d: dict) -> str:
    import json
    return json.dumps(d, default=float)
