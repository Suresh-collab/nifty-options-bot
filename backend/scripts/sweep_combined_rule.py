"""
Parameter sweep for the Combined Rule (signal_engine's _score_to_direction).

Investigates why plain MACD beat the Combined Rule on the 15m shootout. Sweeps:
  - ST weight (current 40)
  - MACD cross weight (current 25)  → trend weight is 0.7*cross
  - RSI weight (current 20)
  - RSI thresholds (current 35/65)
  - Entry threshold (current |score| > 15)

Each config is backtested with the same loop as indicator_shootout.py and
compared against plain MACD as the benchmark.

Usage:
    cd backend
    python -m scripts.sweep_combined_rule --interval 15m --days 60
"""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from indicators.engine import _rsi, _macd, _supertrend
from backtesting.engine import LOT_SIZES, DELTA_FACTOR, IST_OFFSET
from scripts.indicator_shootout import _load_yf, _backtest, _metrics, Trade, _dir_macd


def _direction_for_config(
    df: pd.DataFrame,
    w_st: float, w_macd_cross: float, w_rsi: float,
    rsi_lo: float, rsi_hi: float, entry_threshold: float,
) -> np.ndarray:
    """Reproduces _score_to_direction with configurable weights."""
    rsi = _rsi(df["Close"], 14).values
    macd_line, signal_line, _ = _macd(df["Close"], 12, 26, 9)
    _, st_dir = _supertrend(df["High"], df["Low"], df["Close"], 7, 3.0)
    macd_line = macd_line.values
    signal_line = signal_line.values
    st_dir = st_dir.values

    n = len(df)
    st_score = np.where(st_dir == 1, w_st, -w_st)

    macd_gt = macd_line > signal_line
    macd_gt_prev = np.roll(macd_gt, 1)
    macd_gt_prev[0] = macd_gt[0]
    cross_up = macd_gt & ~macd_gt_prev
    cross_dn = ~macd_gt & macd_gt_prev
    trend_w = 0.7 * w_macd_cross
    macd_score = np.where(cross_up, w_macd_cross,
                  np.where(cross_dn, -w_macd_cross,
                  np.where(macd_gt, trend_w, -trend_w)))

    rsi_score = np.where(rsi < rsi_lo, w_rsi, np.where(rsi > rsi_hi, -w_rsi, 0.0))

    combined = np.clip(st_score + macd_score + rsi_score, -100, 100)
    direction = np.zeros(n, dtype=np.int8)
    direction[combined > entry_threshold] = 1
    direction[combined < -entry_threshold] = -1
    return direction


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="NIFTY", choices=["NIFTY", "BANKNIFTY"])
    p.add_argument("--interval", default="15m")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--sl-pct", type=float, default=0.01)
    p.add_argument("--tp-pct", type=float, default=0.02)
    p.add_argument("--output", default="../tmp/shootout/sweep_results.csv")
    p.add_argument("--top", type=int, default=15, help="Show top-N configs")
    args = p.parse_args()

    print(f"Loading {args.symbol} {args.interval} ({args.days}d)…")
    df = _load_yf(args.symbol, args.interval, args.days)
    print(f"  {len(df)} bars from {df.index[0]} to {df.index[-1]}\n")

    # MACD baseline
    macd_dir = _dir_macd(df)
    macd_trades = _backtest(df, macd_dir, args.symbol, args.capital, args.sl_pct, args.tp_pct)
    baseline = _metrics(macd_trades)
    print(f"BASELINE (plain MACD): trades={baseline['trades']}  "
          f"WR={baseline['win_rate']*100:.1f}%  WilsonLB={baseline['wilson_lb_95']*100:.1f}%  "
          f"Sharpe={baseline['sharpe']:.2f}  PF={baseline['profit_factor']:.2f}\n")

    # Sweep grid
    w_st_vals     = [0, 10, 20, 30, 40, 50]          # current 40
    w_macd_vals   = [15, 25, 35, 45, 60]              # current 25
    w_rsi_vals    = [0, 10, 20, 30]                   # current 20
    rsi_lo_vals   = [25, 30, 35, 40]                  # current 35
    rsi_hi_vals   = [60, 65, 70, 75]                  # current 65
    threshold_vals= [10, 15, 20, 30]                  # current 15

    grid = list(itertools.product(
        w_st_vals, w_macd_vals, w_rsi_vals,
        rsi_lo_vals, rsi_hi_vals, threshold_vals,
    ))
    print(f"Sweeping {len(grid)} configurations…")

    results = []
    for i, (w_st, w_macd, w_rsi, r_lo, r_hi, thr) in enumerate(grid):
        if i and i % 500 == 0:
            print(f"  …{i}/{len(grid)}")
        if r_lo >= r_hi:
            continue
        if w_st == 0 and w_rsi == 0:
            continue  # would just be MACD with extra steps
        direction = _direction_for_config(df, w_st, w_macd, w_rsi, r_lo, r_hi, thr)
        trades = _backtest(df, direction, args.symbol, args.capital, args.sl_pct, args.tp_pct)
        m = _metrics(trades)
        m.update({"w_st": w_st, "w_macd": w_macd, "w_rsi": w_rsi,
                  "rsi_lo": r_lo, "rsi_hi": r_hi, "threshold": thr})
        results.append(m)

    # Filter: need enough trades for Wilson LB to be meaningful (>= 30)
    valid = [r for r in results if r["trades"] >= 30]
    print(f"\n{len(valid)} configs with ≥30 trades (out of {len(results)} total)")

    # Rank by Wilson lower bound on win rate (most honest single metric)
    ranked = sorted(valid, key=lambda r: r["wilson_lb_95"], reverse=True)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["w_st", "w_macd", "w_rsi", "rsi_lo", "rsi_hi", "threshold",
            "trades", "win_rate", "wilson_lb_95", "sharpe", "profit_factor",
            "max_dd", "total_pnl"]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in ranked:
            w.writerow({k: r[k] for k in cols})
    print(f"Wrote {out_path}\n")

    # Print top-N
    print("=" * 100)
    print(f"TOP {args.top} CONFIGS (sorted by Wilson 95% lower bound on win rate)")
    print("=" * 100)
    print(f"{'#':<3}{'wST':>5}{'wMACD':>7}{'wRSI':>6}{'rsiLo':>7}{'rsiHi':>7}{'thr':>5}"
          f"{'Trd':>6}{'WR':>7}{'95%LB':>8}{'Sharpe':>8}{'PF':>7}")
    for i, r in enumerate(ranked[:args.top], 1):
        print(f"{i:<3}{r['w_st']:>5}{r['w_macd']:>7}{r['w_rsi']:>6}{r['rsi_lo']:>7}"
              f"{r['rsi_hi']:>7}{r['threshold']:>5}{r['trades']:>6}"
              f"{r['win_rate']*100:>6.1f}%{r['wilson_lb_95']*100:>7.1f}%"
              f"{r['sharpe']:>8.2f}{r['profit_factor']:>7.2f}")

    # Sharpe ranking too
    print("\n" + "=" * 100)
    print(f"TOP {args.top} CONFIGS (sorted by Sharpe)")
    print("=" * 100)
    sharpe_ranked = sorted(valid, key=lambda r: r["sharpe"], reverse=True)
    print(f"{'#':<3}{'wST':>5}{'wMACD':>7}{'wRSI':>6}{'rsiLo':>7}{'rsiHi':>7}{'thr':>5}"
          f"{'Trd':>6}{'WR':>7}{'95%LB':>8}{'Sharpe':>8}{'PF':>7}")
    for i, r in enumerate(sharpe_ranked[:args.top], 1):
        print(f"{i:<3}{r['w_st']:>5}{r['w_macd']:>7}{r['w_rsi']:>6}{r['rsi_lo']:>7}"
              f"{r['rsi_hi']:>7}{r['threshold']:>5}{r['trades']:>6}"
              f"{r['win_rate']*100:>6.1f}%{r['wilson_lb_95']*100:>7.1f}%"
              f"{r['sharpe']:>8.2f}{r['profit_factor']:>7.2f}")

    print(f"\nBASELINE recap (plain MACD): WR={baseline['win_rate']*100:.1f}%  "
          f"WilsonLB={baseline['wilson_lb_95']*100:.1f}%  Sharpe={baseline['sharpe']:.2f}  "
          f"PF={baseline['profit_factor']:.2f}  Trades={baseline['trades']}")


if __name__ == "__main__":
    main()
