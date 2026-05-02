"""
Phase 4 — Paper broker adapter.

Wraps the existing SQLite paper_trading simulator so it satisfies the
BrokerAdapter protocol.  This is the default adapter when ENABLE_LIVE_BROKER
is false (or when broker_mode == "paper").

Existing simulator behaviour is never changed — this adapter is a thin shim.
"""
from __future__ import annotations

import uuid
from broker.interface import BrokerAdapter, Order, OrderRequest, OrderResult, Position
from paper_trading.simulator import (
    enter_trade, exit_trade, get_history, get_stats,
)


class PaperBrokerAdapter:
    """
    Satisfies BrokerAdapter (structurally — no explicit inheritance needed).

    place_order  → calls enter_trade() using option premium as entry_price
    cancel_order → calls exit_trade() at the last entry price (zero-loss cancel)
    modify_order → not supported in paper mode (returns REJECTED)
    get_positions → derives open positions from get_history()
    get_orders    → maps trade history to Order objects
    """

    # --- BrokerAdapter.place_order -------------------------------------------

    async def place_order(self, req: OrderRequest) -> OrderResult:
        # For options: price field = option premium; strike embedded in symbol
        # e.g. symbol = "NIFTY25MAY22000CE", price = 150.0
        lot_size = _lot_size_for(req.symbol)
        signal = {
            "direction": f"{req.transaction_type}_{req.instrument_type}",
            "source": "broker_adapter",
        }
        try:
            result = enter_trade(
                ticker=_base_ticker(req.symbol),
                strike=_parse_strike(req.symbol),
                direction=f"{req.transaction_type}_{req.instrument_type}",
                entry_price=req.price,
                lots=req.qty,
                lot_size=lot_size,
                signal=signal,
            )
            broker_order_id = f"PAPER-{result['trade_id']}"
            return OrderResult(
                client_order_id=req.client_order_id,
                status="PLACED",
                broker_order_id=broker_order_id,
                message=result.get("message", ""),
                raw_response=result,
            )
        except Exception as exc:
            return OrderResult(
                client_order_id=req.client_order_id,
                status="REJECTED",
                message=str(exc),
            )

    # --- BrokerAdapter.modify_order ------------------------------------------

    async def modify_order(
        self, order_id: str, price: float, qty: int
    ) -> OrderResult:
        # Paper trading does not support in-flight modification
        return OrderResult(
            client_order_id="",
            status="REJECTED",
            broker_order_id=order_id,
            message="Order modification not supported in paper mode",
        )

    # --- BrokerAdapter.cancel_order ------------------------------------------

    async def cancel_order(self, order_id: str) -> OrderResult:
        # order_id format: "PAPER-{trade_id}"
        try:
            trade_id = int(order_id.replace("PAPER-", ""))
        except ValueError:
            return OrderResult(
                client_order_id="",
                status="REJECTED",
                broker_order_id=order_id,
                message=f"Invalid paper order_id: {order_id}",
            )
        # Find entry price and exit at same price (flat cancel)
        history = get_history()
        trade = next((t for t in history if t["id"] == trade_id), None)
        if trade is None:
            return OrderResult(
                client_order_id="",
                status="REJECTED",
                broker_order_id=order_id,
                message=f"Trade {trade_id} not found",
            )
        result = exit_trade(trade_id, trade["entry_price"])
        return OrderResult(
            client_order_id="",
            status="CANCELLED",
            broker_order_id=order_id,
            message="Paper trade cancelled at entry price (zero P&L)",
            raw_response=result,
        )

    # --- BrokerAdapter.get_positions -----------------------------------------

    async def get_positions(self) -> list[Position]:
        history = get_history()
        positions = []
        for t in history:
            if t["status"] != "OPEN":
                continue
            pnl = 0.0
            positions.append(
                Position(
                    symbol=f"{t['ticker']}{int(t['strike'])}",
                    qty=t["lots"] * t["lot_size"],
                    avg_price=float(t["entry_price"]),
                    pnl=pnl,
                    product="MIS",
                    instrument_type=t["direction"].split("_")[-1] if "_" in t["direction"] else "CE",
                )
            )
        return positions

    # --- BrokerAdapter.get_orders --------------------------------------------

    async def get_orders(self) -> list[Order]:
        history = get_history()
        orders = []
        for t in history:
            orders.append(
                Order(
                    broker_order_id=f"PAPER-{t['id']}",
                    client_order_id="",
                    symbol=f"{t['ticker']}{int(t['strike'])}",
                    transaction_type="BUY",
                    qty=t["lots"] * t["lot_size"],
                    price=float(t["entry_price"]),
                    status=_map_status(t["status"]),
                    filled_qty=t["lots"] * t["lot_size"] if t["status"] in ("CLOSED", "HALTED") else 0,
                    average_price=float(t.get("exit_price") or t["entry_price"]),
                )
            )
        return orders


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lot_size_for(symbol: str) -> int:
    s = symbol.upper()
    if "BANKNIFTY" in s:
        return 15
    if "SENSEX" in s:
        return 20
    return 25  # NIFTY default


def _base_ticker(symbol: str) -> str:
    for base in ("BANKNIFTY", "SENSEX", "NIFTY"):
        if symbol.upper().startswith(base):
            return base
    return symbol[:5].upper()


def _parse_strike(symbol: str) -> float:
    """Best-effort: extract numeric strike from e.g. 'NIFTY25MAY22000CE' → 22000."""
    import re
    m = re.search(r"(\d{4,6})(CE|PE)?$", symbol.upper())
    return float(m.group(1)) if m else 0.0


def _map_status(sim_status: str) -> str:
    return {
        "OPEN":   "PLACED",
        "CLOSED": "FILLED",
        "HALTED": "CANCELLED",
    }.get(sim_status, sim_status)
