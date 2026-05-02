"""
Phase 4 — Zerodha Kite Connect adapter.

Implements BrokerAdapter using the kiteconnect library.
kiteconnect is a synchronous library; calls are run in a thread executor
so the FastAPI event loop is never blocked.

IMPORTANT: This adapter is ONLY instantiated when:
  1. ENABLE_LIVE_BROKER=true  (feature flag)
  2. broker_mode="live"       (settings)

Both conditions must be true.  The default is paper mode — real money is
never touched unless the user explicitly sets both.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from broker.interface import BrokerAdapter, Order, OrderRequest, OrderResult, Position

logger = logging.getLogger(__name__)


class ZerodhaKiteAdapter:
    """
    Satisfies BrokerAdapter (structurally).

    Wraps kiteconnect.KiteConnect.  The KiteConnect instance is created once
    at construction time using decrypted credentials from settings.
    """

    def __init__(self, api_key: str, access_token: str):
        # Lazy import — kiteconnect is optional; only needed for live trading
        try:
            from kiteconnect import KiteConnect
        except ImportError as exc:
            raise RuntimeError(
                "kiteconnect package is not installed. "
                "Install it with: pip install kiteconnect"
            ) from exc

        self._kite = KiteConnect(api_key=api_key)
        self._kite.set_access_token(access_token)
        logger.info("ZerodhaKiteAdapter initialised (api_key=%s...)", api_key[:4])

    # ---------------------------------------------------------------------------
    # BrokerAdapter methods
    # ---------------------------------------------------------------------------

    async def place_order(self, req: OrderRequest) -> OrderResult:
        """Place a market/limit order via Kite Connect (runs in executor)."""
        def _place() -> dict:
            return self._kite.place_order(
                variety=self._kite.VARIETY_REGULAR,
                exchange=req.exchange,
                tradingsymbol=req.symbol,
                transaction_type=req.transaction_type,
                quantity=req.qty,
                product=req.product,
                order_type=req.order_type,
                price=req.price if req.order_type != "MARKET" else None,
                trigger_price=req.trigger_price if req.trigger_price else None,
                tag=req.client_order_id[:20],  # Kite tag max 20 chars
            )

        try:
            response = await asyncio.get_event_loop().run_in_executor(None, _place)
            broker_order_id = str(response.get("order_id", ""))
            logger.info("Kite order placed: broker_id=%s client_id=%s",
                        broker_order_id, req.client_order_id)
            return OrderResult(
                client_order_id=req.client_order_id,
                status="PLACED",
                broker_order_id=broker_order_id,
                raw_response=response,
            )
        except Exception as exc:
            logger.warning("Kite place_order failed: %s", exc)
            return OrderResult(
                client_order_id=req.client_order_id,
                status="REJECTED",
                message=str(exc),
            )

    async def modify_order(
        self, order_id: str, price: float, qty: int
    ) -> OrderResult:
        def _modify() -> dict:
            return self._kite.modify_order(
                variety=self._kite.VARIETY_REGULAR,
                order_id=order_id,
                price=price,
                quantity=qty,
            )

        try:
            response = await asyncio.get_event_loop().run_in_executor(None, _modify)
            return OrderResult(
                client_order_id="",
                status="PLACED",
                broker_order_id=order_id,
                raw_response=response,
            )
        except Exception as exc:
            logger.warning("Kite modify_order failed: %s", exc)
            return OrderResult(
                client_order_id="",
                status="REJECTED",
                broker_order_id=order_id,
                message=str(exc),
            )

    async def cancel_order(self, order_id: str) -> OrderResult:
        def _cancel() -> dict:
            return self._kite.cancel_order(
                variety=self._kite.VARIETY_REGULAR,
                order_id=order_id,
            )

        try:
            response = await asyncio.get_event_loop().run_in_executor(None, _cancel)
            return OrderResult(
                client_order_id="",
                status="CANCELLED",
                broker_order_id=order_id,
                raw_response=response,
            )
        except Exception as exc:
            logger.warning("Kite cancel_order failed: %s", exc)
            return OrderResult(
                client_order_id="",
                status="REJECTED",
                broker_order_id=order_id,
                message=str(exc),
            )

    async def get_positions(self) -> list[Position]:
        def _get() -> dict:
            return self._kite.positions()

        try:
            data = await asyncio.get_event_loop().run_in_executor(None, _get)
            positions = []
            for p in data.get("net", []):
                positions.append(Position(
                    symbol=p.get("tradingsymbol", ""),
                    qty=int(p.get("quantity", 0)),
                    avg_price=float(p.get("average_price", 0)),
                    pnl=float(p.get("pnl", 0)),
                    product=p.get("product", "MIS"),
                    instrument_type=p.get("instrument_type", "EQ"),
                ))
            return positions
        except Exception as exc:
            logger.warning("Kite get_positions failed: %s", exc)
            return []

    async def get_orders(self) -> list[Order]:
        def _get() -> list:
            return self._kite.orders()

        try:
            raw_orders = await asyncio.get_event_loop().run_in_executor(None, _get)
            orders = []
            for o in raw_orders:
                orders.append(Order(
                    broker_order_id=str(o.get("order_id", "")),
                    client_order_id=o.get("tag", ""),
                    symbol=o.get("tradingsymbol", ""),
                    transaction_type=o.get("transaction_type", ""),
                    qty=int(o.get("quantity", 0)),
                    price=float(o.get("price", 0)),
                    status=_map_kite_status(o.get("status", "")),
                    filled_qty=int(o.get("filled_quantity", 0)),
                    average_price=float(o.get("average_price", 0)),
                ))
            return orders
        except Exception as exc:
            logger.warning("Kite get_orders failed: %s", exc)
            return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_kite_status(kite_status: str) -> str:
    return {
        "OPEN":        "PLACED",
        "COMPLETE":    "FILLED",
        "REJECTED":    "REJECTED",
        "CANCELLED":   "CANCELLED",
        "TRIGGER PENDING": "PLACED",
    }.get(kite_status.upper(), kite_status)
