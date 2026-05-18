"""
Indicator Shootout — head-to-head backtest of individual indicators, pairwise
combos, the existing rule-based engine, and (optionally) the Phase 2 ML model.

Usage:
    cd backend
    python -m scripts.indicator_shootout --symbol NIFTY --interval 5m --days 59
    python -m scripts.indicator_shootout --include-ml          # also test ML signal
    python -m scripts.indicator_shootout --output results.csv  # custom output path

Honest disclaimers (read these):
  - yfinance hard-caps 5-min data at 60 days. "6 months of 5-min" is not
    achievable from a free public source. We use 59 days (~3,400 bars), which
    is enough for directional ranking but NOT enough for 95%-confidence claims.
  - "95% confidence" requires hundreds-to-thousands of trades per strategy plus
    out-of-sample validation. This script reports Sharpe / Win Rate / MaxDD /
    Profit Factor and a Wilson-95% lower bound on win rate so you can see the
    honest range, not a hand-wavey single number.
  - Single-indicator strategies almost never beat well-tuned combos. The ranking
    is meant to inform — not to be deployed as-is.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Make backend importable when run as a module
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from indicators.engine import _rsi, _macd, _supertrend, _bbands, _ema
from backtesting.engine import _score_to_direction, LOT_SIZES, DELTA_FACTOR, IST_OFFSET


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_yf(symbol: str, interval: str, days: int) -> pd.DataFrame:
    """Fetch OHLCV. yfinance first, then direct Yahoo HTTP API fallback
    (matches data/market_data.py fallback chain)."""
    yf_ticker = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK"}[symbol]
    days = min(days, 59) if interval == "5m" else days

    df = None
    try:
        import yfinance as yf
        df = yf.download(yf_ticker, period=f"{days}d", interval=interval,
                         auto_adjust=False, progress=False)
        if df is None or df.empty:
            df = None
    except Exception as e:
        print(f"  [yfinance] failed: {e}")
        df = None

    if df is None or df.empty:
        print("  [fallback] using direct Yahoo HTTP API…")
        from data.market_data import _fetch_yahoo_direct
        df = _fetch_yahoo_direct(yf_ticker, interval)

    if df is None or df.empty:
        raise RuntimeError(f"all sources failed for {symbol}/{interval}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns=str.capitalize)
    df.index = pd.to_datetime(df.index, utc=True)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


# ─────────────────────────────────────────────────────────────────────────────
# Per-strategy direction generators
# All return int8 array: +1 long, -1 short, 0 flat
# ─────────────────────────────────────────────────────────────────────────────

def _dir_rsi(df: pd.DataFrame) -> np.ndarray:
    r = _rsi(df["Close"], 14).values
    out = np.zeros(len(df), dtype=np.int8)
    out[r < 35] = 1
    out[r > 65] = -1
    return out


def _dir_macd(df: pd.DataFrame) -> np.ndarray:
    m, s, _ = _macd(df["Close"], 12, 26, 9)
    return np.where(m.values > s.values, 1, -1).astype(np.int8)


def _dir_supertrend(df: pd.DataFrame) -> np.ndarray:
    _, st_dir = _supertrend(df["High"], df["Low"], df["Close"], 7, 3.0)
    return st_dir.astype(np.int8).values


def _dir_bbands(df: pd.DataFrame) -> np.ndarray:
    upper, mid, lower = _bbands(df["Close"], 20, 2.0)
    c = df["Close"].values
    out = np.zeros(len(df), dtype=np.int8)
    out[c < lower.values] = 1     # mean-reversion long below lower band
    out[c > upper.values] = -1    # mean-reversion short above upper band
    return out


def _dir_ema(df: pd.DataFrame) -> np.ndarray:
    fast = _ema(df["Close"], 20).values
    slow = _ema(df["Close"], 50).values
    return np.where(fast > slow, 1, -1).astype(np.int8)


def _dir_atr_breakout(df: pd.DataFrame) -> np.ndarray:
    """ATR breakout: long if close > prev close + 1*ATR(14), short if < prev close - 1*ATR(14)."""
    high, low, close = df["High"].values, df["Low"].values, df["Close"].values
    tr = np.maximum.reduce([
        high[1:] - low[1:],
        np.abs(high[1:] - close[:-1]),
        np.abs(low[1:] - close[:-1]),
    ])
    tr = np.concatenate([[tr[0]], tr])
    atr = pd.Series(tr).rolling(14).mean().values
    prev_close = np.concatenate([[close[0]], close[:-1]])
    out = np.zeros(len(df), dtype=np.int8)
    out[close > prev_close + atr] = 1
    out[close < prev_close - atr] = -1
    return out


def _dir_combined_rule(df: pd.DataFrame) -> np.ndarray:
    """The existing production signal_engine rule (RSI + MACD + SuperTrend weighted)."""
    rsi = _rsi(df["Close"], 14).values
    m, s, _ = _macd(df["Close"], 12, 26, 9)
    _, st_dir = _supertrend(df["High"], df["Low"], df["Close"], 7, 3.0)
    return _score_to_direction(st_dir.values, m.values, s.values, rsi)


SINGLE_STRATEGIES = {
    "RSI":         _dir_rsi,
    "MACD":        _dir_macd,
    "SuperTrend":  _dir_supertrend,
    "BBands":      _dir_bbands,
    "EMA 20/50":   _dir_ema,
    "ATR breakout": _dir_atr_breakout,
}

BASELINES = {
    "Combined Rule (current engine)": _dir_combined_rule,
}


def _make_pair(a_name: str, b_name: str):
    """Build a combo strategy: only trade when both indicators agree on direction."""
    fa, fb = SINGLE_STRATEGIES[a_name], SINGLE_STRATEGIES[b_name]
    def fn(df: pd.DataFrame) -> np.ndarray:
        da, db = fa(df), fb(df)
        out = np.zeros(len(df), dtype=np.int8)
        agree_long = (da == 1) & (db == 1)
        agree_short = (da == -1) & (db == -1)
        out[agree_long] = 1
        out[agree_short] = -1
        return out
    return fn


# ─────────────────────────────────────────────────────────────────────────────
# Backtest loop — replicates backtesting/engine._run with an injected direction
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    pnl: float
    win: bool


def _backtest(
    df: pd.DataFrame, direction: np.ndarray,
    symbol: str, capital: float, sl_pct: float, tp_pct: float,
) -> list[Trade]:
    lot_size = LOT_SIZES.get(symbol, 25)
    closes = df["Close"].values
    timestamps = df.index
    trades: list[Trade] = []
    position = 0
    entry_price = 0.0
    lots = 1

    for i in range(50, len(df)):
        ist = timestamps[i] + IST_OFFSET
        is_eod = (ist.hour > 15) or (ist.hour == 15 and ist.minute >= 30)

        if position != 0:
            move = closes[i] - entry_price if position == 1 else entry_price - closes[i]
            sl_hit = closes[i] <= entry_price * (1 - sl_pct) if position == 1 \
                else closes[i] >= entry_price * (1 + sl_pct)
            tp_hit = closes[i] >= entry_price * (1 + tp_pct) if position == 1 \
                else closes[i] <= entry_price * (1 - tp_pct)
            reversed_ = direction[i] == -position

            if sl_hit or tp_hit or is_eod or reversed_:
                pnl = move * lot_size * lots * DELTA_FACTOR
                trades.append(Trade(pnl=pnl, win=pnl > 0))
                position = 0

        if position == 0 and not is_eod and direction[i] != 0:
            spot = closes[i]
            lots = max(1, int(capital / (spot * lot_size * DELTA_FACTOR)))
            position = int(direction[i])
            entry_price = closes[i]

    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────

def _wilson_lower(wins: int, n: int, z: float = 1.96) -> float:
    """Wilson 95% lower bound on win-rate. Honest small-sample CI."""
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - spread) / denom)


def _metrics(trades: list[Trade]) -> dict:
    n = len(trades)
    if n == 0:
        return {
            "trades": 0, "win_rate": 0.0, "wilson_lb_95": 0.0,
            "total_pnl": 0.0, "sharpe": 0.0,
            "max_dd": 0.0, "profit_factor": 0.0, "avg_pnl": 0.0,
        }
    pnls = np.array([t.pnl for t in trades])
    wins = int(sum(t.win for t in trades))
    gross_profit = pnls[pnls > 0].sum()
    gross_loss = -pnls[pnls < 0].sum()
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Equity curve & drawdown
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min())

    # Sharpe (per-trade, annualised by sqrt(252) — rough approximation)
    sharpe = (pnls.mean() / pnls.std()) * math.sqrt(252) if pnls.std() > 0 else 0.0

    return {
        "trades": n,
        "win_rate": wins / n,
        "wilson_lb_95": _wilson_lower(wins, n),
        "total_pnl": float(pnls.sum()),
        "sharpe": float(sharpe),
        "max_dd": max_dd,
        "profit_factor": float(pf) if pf != float("inf") else 999.0,
        "avg_pnl": float(pnls.mean()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

async def _maybe_ml_signal(df: pd.DataFrame, symbol: str, interval: str) -> np.ndarray | None:
    """Try to use the Phase 2 ML model. Returns None if unavailable."""
    try:
        from ml.registry import load_model
        from ml.features import build_features
    except Exception as e:
        print(f"  [ml] skipped (import failed: {e})")
        return None
    try:
        model = await load_model("direction", symbol=symbol, interval=interval)
        if model is None:
            print("  [ml] skipped (no active model in registry)")
            return None
        feats = build_features(df)
        proba = model.predict_proba(feats.values)
        out = np.zeros(len(df), dtype=np.int8)
        # Pad to match df length (features drop warm-up rows)
        offset = len(df) - len(proba)
        out[offset:][proba[:, 1] > 0.55] = 1
        out[offset:][proba[:, 0] > 0.55] = -1
        return out
    except Exception as e:
        print(f"  [ml] skipped (runtime error: {e})")
        return None


def run_shootout(
    symbol: str, interval: str, days: int,
    capital: float, sl_pct: float, tp_pct: float,
    include_pairs: bool, include_ml: bool,
) -> list[dict]:
    print(f"Loading {symbol} {interval} ({days}d)…")
    df = _load_yf(symbol, interval, days)
    print(f"  {len(df)} bars from {df.index[0]} to {df.index[-1]}")

    strategies: dict[str, callable] = {}
    strategies.update(SINGLE_STRATEGIES)
    strategies.update(BASELINES)
    if include_pairs:
        names = list(SINGLE_STRATEGIES.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                strategies[f"{names[i]} + {names[j]}"] = _make_pair(names[i], names[j])

    if include_ml:
        ml_dir = asyncio.run(_maybe_ml_signal(df, symbol, interval))
        if ml_dir is not None:
            strategies["ML Signal (Phase 2)"] = lambda _df, d=ml_dir: d

    results = []
    for name, fn in strategies.items():
        direction = fn(df)
        trades = _backtest(df, direction, symbol, capital, sl_pct, tp_pct)
        m = _metrics(trades)
        m["strategy"] = name
        results.append(m)
        print(f"  {name:<40s} trades={m['trades']:>4d}  WR={m['win_rate']*100:5.1f}%  "
              f"WilsonLB={m['wilson_lb_95']*100:5.1f}%  Sharpe={m['sharpe']:6.2f}  "
              f"MaxDD={m['max_dd']:>10.0f}  PF={m['profit_factor']:5.2f}")

    return results


def write_csv(results: list[dict], path: Path) -> None:
    if not results:
        return
    cols = ["strategy", "trades", "win_rate", "wilson_lb_95", "sharpe",
            "profit_factor", "max_dd", "total_pnl", "avg_pnl"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in results:
            w.writerow({k: r[k] for k in cols})
    print(f"\nWrote {path}")


def print_ranking(results: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("HONEST RANKING (sorted by Sharpe, with caveats)")
    print("=" * 78)
    ranked = sorted(results, key=lambda r: r["sharpe"], reverse=True)
    print(f"{'#':<3}{'Strategy':<40}{'Sharpe':>8}{'WR':>7}{'95%LB':>8}{'Trades':>8}")
    for i, r in enumerate(ranked, 1):
        print(f"{i:<3}{r['strategy']:<40}{r['sharpe']:>8.2f}"
              f"{r['win_rate']*100:>6.1f}%{r['wilson_lb_95']*100:>7.1f}%{r['trades']:>8}")
    print("\nNote: 'WR' is point estimate; '95%LB' is the Wilson lower bound — i.e.")
    print("the win rate we can be 95% confident the strategy is AT LEAST achieving.")
    print("If WR=55% but 95%LB=42%, the sample is too small to claim an edge.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="NIFTY", choices=["NIFTY", "BANKNIFTY"])
    p.add_argument("--interval", default="5m")
    p.add_argument("--days", type=int, default=59,
                   help="Lookback days. yfinance caps 5m data at 60.")
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--sl-pct", type=float, default=0.01)
    p.add_argument("--tp-pct", type=float, default=0.02)
    p.add_argument("--no-pairs", action="store_true",
                   help="Skip pairwise combos (faster).")
    p.add_argument("--include-ml", action="store_true",
                   help="Also test the Phase 2 ML model (requires trained model in registry).")
    p.add_argument("--output", default="shootout_results.csv")
    args = p.parse_args()

    results = run_shootout(
        symbol=args.symbol, interval=args.interval, days=args.days,
        capital=args.capital, sl_pct=args.sl_pct, tp_pct=args.tp_pct,
        include_pairs=not args.no_pairs, include_ml=args.include_ml,
    )
    write_csv(results, Path(args.output))
    print_ranking(results)


if __name__ == "__main__":
    main()
