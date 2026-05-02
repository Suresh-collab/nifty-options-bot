import sqlite3
import json
from datetime import datetime
from pathlib import Path

import os

# On Vercel, filesystem is read-only except /tmp
if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/paper_trades.db")
else:
    DB_PATH = Path(__file__).parent.parent / "paper_trades.db"

def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT,
            strike      REAL,
            direction   TEXT,
            entry_price REAL,
            exit_price  REAL,
            lots        INTEGER,
            lot_size    INTEGER,
            status      TEXT DEFAULT 'OPEN',
            entry_time  TEXT,
            exit_time   TEXT,
            pnl         REAL DEFAULT 0,
            signal_json TEXT
        )""")
        conn.commit()

def enter_trade(ticker: str, strike: float, direction: str,
                entry_price: float, lots: int, lot_size: int,
                signal: dict) -> dict:
    init_db()
    entry_time = datetime.now().isoformat()
    with _get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO trades
            (ticker, strike, direction, entry_price, lots, lot_size,
             status, entry_time, signal_json)
            VALUES (?,?,?,?,?,?,'OPEN',?,?)
        """, (ticker, strike, direction, entry_price, lots, lot_size,
              entry_time, json.dumps(signal)))
        conn.commit()
        trade_id = cur.lastrowid
    return {"trade_id": trade_id, "status": "OPEN", "entry_time": entry_time,
            "message": f"Paper trade entered: {direction} {ticker} {strike} CE/PE"}

def exit_trade(trade_id: int, exit_price: float) -> dict:
    init_db()
    exit_time = datetime.now().isoformat()
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row:
            return {"error": "Trade not found"}
        if row["status"] == "CLOSED":
            return {"error": "Trade already closed"}
        pnl = (exit_price - row["entry_price"]) * row["lots"] * row["lot_size"]
        if "PE" in row["direction"]:
            pnl = (row["entry_price"] - exit_price) * row["lots"] * row["lot_size"]
        conn.execute("""
            UPDATE trades SET exit_price=?, exit_time=?, status='CLOSED', pnl=?
            WHERE id=?
        """, (exit_price, exit_time, round(pnl, 2), trade_id))
        conn.commit()
    return {"trade_id": trade_id, "status": "CLOSED",
            "exit_price": exit_price, "pnl": round(pnl, 2)}

def get_history() -> list:
    init_db()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY entry_time DESC LIMIT 100"
        ).fetchall()
    return [dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Phase 3 — risk-engine helpers (additive; existing functions unchanged)
# ---------------------------------------------------------------------------

def get_daily_pnl() -> float:
    """Sum of P&L for all trades closed today (IST date)."""
    init_db()
    today = datetime.now().strftime("%Y-%m-%d")
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT pnl FROM trades WHERE status='CLOSED' AND exit_time LIKE ?",
            (f"{today}%",),
        ).fetchall()
    return round(sum(r["pnl"] for r in rows), 2)


def get_open_count() -> int:
    """Number of currently open paper trades."""
    init_db()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM trades WHERE status='OPEN'"
        ).fetchone()
    return int(row["cnt"])


def halt_all_open() -> list[dict]:
    """
    Mark every OPEN trade as HALTED (kill-switch action).
    Returns the list of halted trade IDs and tickers.
    """
    init_db()
    halt_time = datetime.now().isoformat()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, ticker, direction FROM trades WHERE status='OPEN'"
        ).fetchall()
        if rows:
            conn.execute(
                "UPDATE trades SET status='HALTED', exit_time=? WHERE status='OPEN'",
                (halt_time,),
            )
            conn.commit()
    return [{"trade_id": r["id"], "ticker": r["ticker"], "direction": r["direction"]} for r in rows]


def get_stats() -> dict:
    init_db()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE status='CLOSED'"
        ).fetchall()
    if not rows:
        return {"total_trades": 0, "win_rate": 0, "total_pnl": 0,
                "avg_pnl": 0, "best_trade": 0, "worst_trade": 0}
    pnls = [r["pnl"] for r in rows]
    wins = [p for p in pnls if p > 0]
    return {
        "total_trades":  len(pnls),
        "open_trades":   sum(1 for r in conn.execute(
                             "SELECT id FROM trades WHERE status='OPEN'").fetchall()),
        "win_rate":      round(len(wins) / len(pnls) * 100, 1),
        "total_pnl":     round(sum(pnls), 2),
        "avg_pnl":       round(sum(pnls) / len(pnls), 2),
        "best_trade":    round(max(pnls), 2),
        "worst_trade":   round(min(pnls), 2),
    }
