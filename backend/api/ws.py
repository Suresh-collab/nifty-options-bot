"""
Phase 5.1 — WebSocket endpoint for live P&L + position updates.

Architecture:
  - /ws/live  : clients connect here; they receive JSON ticks on every broadcast
  - broadcast(): called by the background poller or trade events to push data
  - _pnl_poller(): asyncio background task started in main.py on startup;
                   reads paper-trade state every second and broadcasts if changed

TDD 5.1: 3 clients connected → all receive a tick within 500 ms of server event.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

ws_router = APIRouter()

# ---------------------------------------------------------------------------
# Connection registry
# ---------------------------------------------------------------------------
_clients: set[WebSocket] = set()


async def broadcast(data: dict[str, Any]) -> None:
    """Push *data* as JSON to every connected WebSocket client."""
    dead: set[WebSocket] = set()
    for ws in list(_clients):
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)
    if dead:
        logger.debug("Removed %d dead WebSocket client(s)", len(dead))


def connected_count() -> int:
    return len(_clients)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@ws_router.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    """
    Live P&L stream.  Clients connect and receive JSON ticks:
      { "type": "pnl_update", "open_trades": [...], "daily_pnl": float, "stats": {...} }
    Clients may send any text to keep the connection alive.
    """
    await ws.accept()
    _clients.add(ws)
    logger.info("WebSocket client connected (%d total)", len(_clients))
    try:
        while True:
            # Block until client sends something (keep-alive ping) or disconnects
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)
        logger.info("WebSocket client disconnected (%d remaining)", len(_clients))


# ---------------------------------------------------------------------------
# Background P&L poller
# ---------------------------------------------------------------------------

async def _pnl_poller(interval: float = 1.0) -> None:
    """
    Runs as a FastAPI lifespan background task.
    Reads open paper trades + daily P&L every *interval* seconds and
    broadcasts to all connected clients.  Only broadcasts when there are
    connected clients (no wasted work when nobody is watching).
    """
    from paper_trading.simulator import get_history, get_stats, get_daily_pnl

    last_payload: dict | None = None

    while True:
        try:
            await asyncio.sleep(interval)
            if not _clients:
                continue

            open_trades = [t for t in get_history() if t["status"] == "OPEN"]
            daily_pnl   = get_daily_pnl()
            stats       = get_stats()

            payload = {
                "type":        "pnl_update",
                "open_trades": open_trades,
                "daily_pnl":   daily_pnl,
                "stats":       stats,
            }

            # Only push when data changed (reduces client-side re-renders)
            if payload != last_payload:
                await broadcast(payload)
                last_payload = payload

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("P&L poller error: %s", exc)


async def start_pnl_poller(interval: float = 1.0) -> asyncio.Task:
    """Start the background poller and return the Task (so main.py can cancel it)."""
    return asyncio.create_task(_pnl_poller(interval), name="pnl_poller")
