"""
Persist option-chain snapshots into oi_snapshots so OI Buildup can be
forward-tested over weeks/months.

Wire this into the WS poller or scheduler so every successful chain fetch
appends a row. Synthetic-fallback chains are silently skipped.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import get_session_factory
from indicators.oi_flow import classify_oi_flow

logger = logging.getLogger(__name__)


# In-memory hold of the previous snapshot per symbol so we can diff against it.
# This is intentionally a process-local cache — restarting the BE simply means
# the first new snapshot has no prior to diff against (regime = NEUTRAL).
_prev_chain: dict[str, dict] = {}


async def log_oi_snapshot(chain: dict) -> Optional[str]:
    """
    Persist a single option-chain snapshot. Returns the new row's UUID as str,
    or None if the chain is unreliable or DB write failed.

    Safe to call inside a tight poll loop — silently no-ops on fallback chains.
    """
    if chain.get("fallback") is True:
        return None

    symbol = chain.get("ticker")
    spot = float(chain.get("spot") or 0)
    if not symbol or spot <= 0:
        return None

    prev = _prev_chain.get(symbol)
    flow = classify_oi_flow(prev, chain) if prev else {
        "regime":       "BOOTSTRAP",
        "bias_score":   0.0,
        "ce_oi_change": 0,
        "pe_oi_change": 0,
    }
    _prev_chain[symbol] = chain   # update cache regardless

    factory = get_session_factory()
    try:
        async with factory() as session:
            return await _insert(session, chain, flow, symbol, spot)
    except Exception as exc:                   # pragma: no cover - integration path
        logger.warning("oi_snapshot insert failed for %s: %s", symbol, exc)
        return None


async def _insert(
    session: AsyncSession,
    chain: dict,
    flow: dict,
    symbol: str,
    spot: float,
) -> str:
    stmt = text(
        """
        INSERT INTO oi_snapshots
          (symbol, ts, spot, expiry, pcr,
           total_ce_oi, total_pe_oi,
           atm_ce_oi_chg, atm_pe_oi_chg,
           regime, bias_score, strikes_json)
        VALUES
          (:symbol, :ts, :spot, :expiry, :pcr,
           :total_ce_oi, :total_pe_oi,
           :atm_ce_oi_chg, :atm_pe_oi_chg,
           :regime, :bias_score, CAST(:strikes_json AS JSONB))
        RETURNING id
        """
    )
    row = await session.execute(stmt, {
        "symbol":         symbol,
        "ts":             datetime.now(timezone.utc),
        "spot":           spot,
        "expiry":         chain.get("expiry"),
        "pcr":            float(chain.get("pcr") or 0),
        "total_ce_oi":    int(chain.get("total_ce_oi") or 0),
        "total_pe_oi":    int(chain.get("total_pe_oi") or 0),
        "atm_ce_oi_chg":  int(flow.get("ce_oi_change") or 0),
        "atm_pe_oi_chg":  int(flow.get("pe_oi_change") or 0),
        "regime":         flow.get("regime"),
        "bias_score":     float(flow.get("bias_score") or 0),
        "strikes_json":   json.dumps(chain.get("strikes") or []),
    })
    await session.commit()
    new_id = row.scalar()
    return str(new_id) if new_id else ""


def get_cached_prev(symbol: str) -> dict | None:
    """Inspect the in-memory prior snapshot used for diffing. Test helper."""
    return _prev_chain.get(symbol)


def clear_cache() -> None:
    """Drop the in-memory prior snapshots. Useful for tests and process restart."""
    _prev_chain.clear()
