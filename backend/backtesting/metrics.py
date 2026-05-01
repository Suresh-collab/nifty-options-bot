"""
Backtesting performance metrics.

All functions take a list of completed trade dicts:
  {"pnl": float, "entry_ts": datetime, "exit_ts": datetime, ...}
"""

from __future__ import annotations

import math
from typing import TypedDict


class TradeResult(TypedDict):
    entry_ts: str    # ISO string
    exit_ts: str
    symbol: str
    direction: str   # BUY_CE | BUY_PE
    entry_price: float
    exit_price: float
    qty: int
    pnl: float


def win_rate(trades: list[TradeResult]) -> float:
    """Fraction of trades with pnl > 0."""
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t["pnl"] > 0)
    return wins / len(trades)


def net_pnl(trades: list[TradeResult]) -> float:
    return sum(t["pnl"] for t in trades)


def profit_factor(trades: list[TradeResult]) -> float:
    """Gross profit / gross loss. Returns inf when there are no losing trades."""
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def expectancy(trades: list[TradeResult]) -> float:
    """Average P&L per trade."""
    if not trades:
        return 0.0
    return net_pnl(trades) / len(trades)


def max_drawdown(trades: list[TradeResult]) -> float:
    """Maximum peak-to-trough drawdown in P&L units."""
    if not trades:
        return 0.0
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t["pnl"]
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return max_dd


def sharpe_ratio(trades: list[TradeResult], risk_free_daily: float = 0.0) -> float:
    """
    Annualised Sharpe ratio using per-trade P&L as returns.
    Uses sqrt(252) scaling (daily bar assumption).
    Returns 0.0 when std dev is zero or fewer than 2 trades.
    """
    if len(trades) < 2:
        return 0.0
    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    mean = sum(pnls) / n
    variance = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    daily_sharpe = (mean - risk_free_daily) / std
    return daily_sharpe * math.sqrt(252)


def compute_all(trades: list[TradeResult]) -> dict:
    """Return all metrics in a single dict."""
    return {
        "total_trades": len(trades),
        "win_rate": round(win_rate(trades), 4),
        "net_pnl": round(net_pnl(trades), 2),
        "profit_factor": round(profit_factor(trades), 4),
        "expectancy": round(expectancy(trades), 2),
        "max_drawdown": round(max_drawdown(trades), 2),
        "sharpe_ratio": round(sharpe_ratio(trades), 4),
    }
