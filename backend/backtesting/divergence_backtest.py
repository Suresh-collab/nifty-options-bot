"""
Divergence-only backtest.

Mirrors the trade model of backtesting/engine.py but the entry signal comes
exclusively from indicators.divergence.detect_divergence(). This isolates the
edge (or lack of edge) of RSI/price divergence as a standalone signal.

Trade model
-----------
- Entry  : close of the bar where divergence is CONFIRMED (no look-ahead)
- Exit   : first of {SL hit, TP hit, max_hold_bars reached, signal reversal}
- SL/TP  : multiplier of bar's ATR at entry (regime-adjusted vs fixed-pct)
- P&L    : underlying move × lot_size × lots × DELTA_FACTOR  (matches engine.py)
- Sizing : lots = floor(capital / (spot × lot_size × DELTA_FACTOR))

This file lives next to backtesting/engine.py so it can be imported in
parallel with the baseline runner for side-by-side comparison.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from indicators.engine import _rsi
from indicators.divergence import detect_divergence
from backtesting.metrics import TradeResult, compute_all
from backtesting.engine import LOT_SIZES, DELTA_FACTOR


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=length).mean()


def _run_divergence(
    df: pd.DataFrame,
    symbol: str,
    capital: float,
    sl_atr_mult: float,
    tp_atr_mult: float,
    max_hold_bars: int,
    pivot_lookback: int,
    max_lookback_bars: int,
) -> list[TradeResult]:
    lot_size = LOT_SIZES.get(symbol, 25)

    df = df.rename(columns={"o": "Open", "h": "High", "l": "Low",
                            "c": "Close", "v": "Volume"})
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 50:
        return []

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    rsi = _rsi(close, length=14)
    atr = _atr(high, low, close, length=14)
    signal_arr, _events = detect_divergence(
        close,
        rsi=rsi,
        pivot_lookback=pivot_lookback,
        max_lookback_bars=max_lookback_bars,
        include_hidden=False,
    )

    closes = close.values
    atrs = atr.values
    timestamps = df.index

    trades: list[TradeResult] = []
    position = 0
    entry_price = 0.0
    entry_idx = 0
    entry_atr = 0.0
    lots = 1

    warmup = max(50, pivot_lookback + 14)
    for i in range(warmup, len(df)):
        if position != 0:
            held = i - entry_idx
            underlying_move = (
                closes[i] - entry_price if position == 1 else entry_price - closes[i]
            )
            sl_hit = underlying_move <= -sl_atr_mult * entry_atr
            tp_hit = underlying_move >= tp_atr_mult * entry_atr
            reversed_ = signal_arr[i] == -position
            timed_out = held >= max_hold_bars

            if sl_hit or tp_hit or reversed_ or timed_out:
                trades.append({
                    "entry_ts":    timestamps[entry_idx].isoformat(),
                    "exit_ts":     timestamps[i].isoformat(),
                    "symbol":      symbol,
                    "direction":   "BUY_CE" if position == 1 else "BUY_PE",
                    "entry_price": round(entry_price, 2),
                    "exit_price":  round(closes[i], 2),
                    "qty":         lots,
                    "pnl":         round(underlying_move * lot_size * lots * DELTA_FACTOR, 2),
                })
                position = 0

        if position == 0 and signal_arr[i] != 0 and not np.isnan(atrs[i]) and atrs[i] > 0:
            spot = closes[i]
            lots = max(1, int(capital / (spot * lot_size * DELTA_FACTOR)))
            position = int(signal_arr[i])
            entry_price = spot
            entry_idx = i
            entry_atr = float(atrs[i])

    return trades


def run_divergence_backtest(
    df: pd.DataFrame,
    symbol: str,
    capital: float = 100_000.0,
    sl_atr_mult: float = 1.5,
    tp_atr_mult: float = 3.0,
    max_hold_bars: int = 10,
    pivot_lookback: int = 5,
    max_lookback_bars: int = 60,
) -> dict[str, Any]:
    """
    Backtest the RSI/price divergence detector as a standalone signal.

    Default risk model is ATR-based (regime-adjusted) rather than fixed %.
    SL = 1.5 ATR, TP = 3.0 ATR -> reward:risk ≈ 2:1
    max_hold_bars=10 caps how long a trade can sit on (10 days for 1d bars).
    """
    if df.empty:
        return {"trades": [], "metrics": compute_all([]), "equity_curve": []}

    trades = _run_divergence(
        df, symbol, capital,
        sl_atr_mult=sl_atr_mult, tp_atr_mult=tp_atr_mult,
        max_hold_bars=max_hold_bars,
        pivot_lookback=pivot_lookback,
        max_lookback_bars=max_lookback_bars,
    )
    metrics = compute_all(trades)
    equity = 0.0
    curve = []
    for t in trades:
        equity += t["pnl"]
        curve.append({"ts": t["exit_ts"], "equity": round(equity, 2)})
    return {"trades": trades, "metrics": metrics, "equity_curve": curve}
