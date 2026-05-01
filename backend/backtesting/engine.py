"""
Vectorized backtesting engine.

Replays the current rule-based signal engine against historical OHLCV data stored
in ohlcv_cache. Computes indicators once on the full DataFrame, then scans bars
for entry/exit conditions.

Trade model
-----------
- Entry: close price of the signal bar
- Exit: first of (SL hit | TP hit | EOD | signal reversal)
- SL:   entry_price × (1 ∓ sl_pct) on the underlying
- TP:   entry_price × (1 ± tp_pct) on the underlying
- P&L:  underlying point move × lot_size × lots × DELTA_FACTOR
        where DELTA_FACTOR=0.5 approximates ATM option delta

Lots are derived from capital:  lots = floor(capital / (spot × lot_size × DELTA_FACTOR))
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from indicators.engine import _rsi, _macd, _supertrend, _bbands
from backtesting.metrics import TradeResult, compute_all

logger = logging.getLogger(__name__)

LOT_SIZES: dict[str, int] = {"NIFTY": 25, "BANKNIFTY": 15}
DELTA_FACTOR = 0.5   # ATM option delta approximation
IST_OFFSET = pd.Timedelta(hours=5, minutes=30)
EOD_TIME = pd.Timedelta(hours=15, minutes=30)   # 15:30 IST


def _score_to_direction(
    st_dir: np.ndarray,          # +1 / -1
    macd_line: np.ndarray,
    signal_line: np.ndarray,
    rsi: np.ndarray,
) -> np.ndarray:
    """Return int array: +1 = BUY_CE, -1 = BUY_PE, 0 = AVOID."""
    n = len(st_dir)

    # --- SuperTrend score (+/- 40) ---
    st_score = np.where(st_dir == 1, 40.0, -40.0)

    # --- MACD score ---
    macd_gt = macd_line > signal_line
    macd_gt_prev = np.roll(macd_gt, 1)
    macd_gt_prev[0] = macd_gt[0]
    cross_up = macd_gt & ~macd_gt_prev      # BUY cross  → +25
    cross_dn = ~macd_gt & macd_gt_prev      # SELL cross → -25
    macd_score = np.where(cross_up, 25.0,
                 np.where(cross_dn, -25.0,
                 np.where(macd_gt, 17.5, -17.5)))   # BULLISH/BEARISH → ±0.7*25

    # --- RSI score ---
    rsi_score = np.where(rsi < 35, 20.0, np.where(rsi > 65, -20.0, 0.0))

    # PCR is unavailable historically → 0 contribution (neutral)
    combined = st_score + macd_score + rsi_score  # range ~ [-85, +85]
    combined = np.clip(combined, -100, 100)

    # Mirror signal_engine.py thresholds exactly
    direction = np.zeros(n, dtype=np.int8)
    direction[combined > 10] = 1    # BUY_CE
    direction[combined < -10] = -1  # BUY_PE
    # Low confidence guard: if |score| < 15 it stays 0 (AVOID)
    direction[np.abs(combined) < 15] = 0

    return direction


def _run(df: pd.DataFrame, symbol: str, capital: float, sl_pct: float, tp_pct: float) -> list[TradeResult]:
    """Core backtesting loop on a single symbol's OHLCV DataFrame."""
    lot_size = LOT_SIZES.get(symbol, 25)

    # Rename to match indicator engine expectations
    df = df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    if len(df) < 50:  # need enough bars for warm-up
        return []

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # Pre-compute all indicators vectorized
    rsi_s = _rsi(close, 14).values
    macd_line, signal_line, _ = _macd(close, 12, 26, 9)
    _, st_dir = _supertrend(high, low, close, 7, 3.0)

    direction_arr = _score_to_direction(
        st_dir.values,
        macd_line.values,
        signal_line.values,
        rsi_s,
    )

    closes = close.values
    highs = high.values
    lows = low.values
    opens = df["Open"].values
    timestamps = df.index  # DatetimeTzDtype (UTC)

    trades: list[TradeResult] = []
    position: int = 0      # +1 = long CE, -1 = long PE, 0 = flat
    entry_price: float = 0.0
    entry_ts_idx: int = 0
    lots: int = 1

    for i in range(50, len(df)):  # skip warm-up bars
        # EOD check: close any open position at 15:30 IST
        ist_time = timestamps[i] + IST_OFFSET
        is_eod = (ist_time.hour > 15) or (ist_time.hour == 15 and ist_time.minute >= 30)

        if position != 0:
            underlying_move = closes[i] - entry_price if position == 1 else entry_price - closes[i]
            sl_hit = closes[i] <= entry_price * (1 - sl_pct) if position == 1 else closes[i] >= entry_price * (1 + sl_pct)
            tp_hit = closes[i] >= entry_price * (1 + tp_pct) if position == 1 else closes[i] <= entry_price * (1 - tp_pct)
            signal_reversed = direction_arr[i] == -position

            if sl_hit or tp_hit or is_eod or signal_reversed:
                exit_price = closes[i]
                pnl = underlying_move * lot_size * lots * DELTA_FACTOR
                trades.append({
                    "entry_ts": timestamps[entry_ts_idx].isoformat(),
                    "exit_ts": timestamps[i].isoformat(),
                    "symbol": symbol,
                    "direction": "BUY_CE" if position == 1 else "BUY_PE",
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "qty": lots,
                    "pnl": round(pnl, 2),
                })
                position = 0

        # Open new position if flat and we have a non-EOD signal
        if position == 0 and not is_eod and direction_arr[i] != 0:
            spot = closes[i]
            lots = max(1, int(capital / (spot * lot_size * DELTA_FACTOR)))
            position = int(direction_arr[i])
            entry_price = closes[i]
            entry_ts_idx = i

    return trades


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    capital: float = 100_000.0,
    sl_pct: float = 0.01,
    tp_pct: float = 0.02,
) -> dict[str, Any]:
    """
    Run a backtest on the provided OHLCV DataFrame.

    Parameters
    ----------
    df      : DataFrame with columns o, h, l, c, v; DatetimeTzIndex (UTC)
    symbol  : "NIFTY" or "BANKNIFTY"
    capital : Trading capital in INR
    sl_pct  : Stop-loss as fraction of entry price (default 1%)
    tp_pct  : Take-profit as fraction of entry price (default 2%)

    Returns
    -------
    dict with keys: trades (list), metrics (dict), equity_curve (list of {ts, equity})
    """
    if df.empty:
        return {"trades": [], "metrics": compute_all([]), "equity_curve": []}

    trades = _run(df, symbol, capital, sl_pct, tp_pct)
    metrics = compute_all(trades)

    # Build equity curve
    equity = 0.0
    equity_curve = []
    for t in trades:
        equity += t["pnl"]
        equity_curve.append({"ts": t["exit_ts"], "equity": round(equity, 2)})

    return {"trades": trades, "metrics": metrics, "equity_curve": equity_curve}


def benchmark_buy_hold(df: pd.DataFrame, capital: float = 100_000.0) -> list[dict]:
    """
    Simple Nifty buy-and-hold benchmark: 1 unit of index, scaled by capital.
    Returns equity curve list: [{ts, equity}, ...].
    """
    if df.empty:
        return []
    close = df["c"] if "c" in df.columns else df["Close"]
    entry = float(close.iloc[0])
    units = capital / entry
    curve = []
    for ts, price in close.items():
        equity = (float(price) - entry) * units
        curve.append({"ts": ts.isoformat(), "equity": round(equity, 2)})
    return curve
