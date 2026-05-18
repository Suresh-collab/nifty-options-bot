"""
Walk-forward validation of the Combined Rule weight sweep.

Splits the dataset into TRAIN (first 67%) and TEST (last 33%), runs the same
weight grid on both halves independently, and ranks configs by **out-of-sample
TEST performance among those that also performed well in TRAIN**.

A config is "robust" if:
  - TRAIN trades >= 20 AND TEST trades >= 10
  - TRAIN Wilson LB > baseline_train_wilson_lb  (beats train baseline)
  - TEST  Wilson LB > baseline_test_wilson_lb   (beats test baseline — the real test)

Configs that only win in-sample but lose out-of-sample are overfit and rejected.

Usage:
    cd backend
    python -m scripts.walkforward_combined_rule --interval 15m --days 60
"""

from __future__ import annotations

import argparse
import csv
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.indicator_shootout import _load_yf, _backtest, _metrics, _dir_macd
from scripts.sweep_combined_rule import _direction_for_config


def _split(df: pd.DataFrame, train_frac: float = 0.67) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = len(df)
    cut = int(n * train_frac)
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


def _score(df: pd.DataFrame, direction_fn, symbol, capital, sl_pct, tp_pct) -> dict:
    direction = direction_fn(df)
    trades = _backtest(df, direction, symbol, capital, sl_pct, tp_pct)
    return _metrics(trades)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="NIFTY", choices=["NIFTY", "BANKNIFTY"])
    p.add_argument("--interval", default="15m")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--sl-pct", type=float, default=0.01)
    p.add_argument("--tp-pct", type=float, default=0.02)
    p.add_argument("--train-frac", type=float, default=0.67)
    p.add_argument("--output", default="../tmp/shootout/walkforward_results.csv")
    p.add_argument("--top", type=int, default=15)
    args = p.parse_args()

    print(f"Loading {args.symbol} {args.interval} ({args.days}d)...")
    df = _load_yf(args.symbol, args.interval, args.days)
    train_df, test_df = _split(df, args.train_frac)
    print(f"  Total {len(df)} bars")
    print(f"  TRAIN: {len(train_df)} bars  ({train_df.index[0]} -> {train_df.index[-1]})")
    print(f"  TEST:  {len(test_df)} bars  ({test_df.index[0]} -> {test_df.index[-1]})\n")

    # Baselines (plain MACD)
    bt_train = _score(train_df, _dir_macd, args.symbol, args.capital, args.sl_pct, args.tp_pct)
    bt_test  = _score(test_df,  _dir_macd, args.symbol, args.capital, args.sl_pct, args.tp_pct)
    print(f"BASELINE plain MACD (TRAIN): trades={bt_train['trades']}  "
          f"WR={bt_train['win_rate']*100:.1f}%  LB={bt_train['wilson_lb_95']*100:.1f}%  "
          f"Sharpe={bt_train['sharpe']:.2f}  PF={bt_train['profit_factor']:.2f}")
    print(f"BASELINE plain MACD (TEST):  trades={bt_test['trades']}  "
          f"WR={bt_test['win_rate']*100:.1f}%  LB={bt_test['wilson_lb_95']*100:.1f}%  "
          f"Sharpe={bt_test['sharpe']:.2f}  PF={bt_test['profit_factor']:.2f}\n")

    # Sweep grid (same as sweep_combined_rule.py)
    w_st_vals      = [0, 10, 20, 30, 40, 50]
    w_macd_vals    = [15, 25, 35, 45, 60]
    w_rsi_vals     = [0, 10, 20, 30]
    rsi_lo_vals    = [25, 30, 35, 40]
    rsi_hi_vals    = [60, 65, 70, 75]
    threshold_vals = [10, 15, 20, 30]

    grid = list(itertools.product(
        w_st_vals, w_macd_vals, w_rsi_vals,
        rsi_lo_vals, rsi_hi_vals, threshold_vals,
    ))
    print(f"Walk-forward over {len(grid)} configs...")

    results = []
    for i, (w_st, w_macd, w_rsi, r_lo, r_hi, thr) in enumerate(grid):
        if i and i % 1000 == 0:
            print(f"  ...{i}/{len(grid)}")
        if r_lo >= r_hi:
            continue
        if w_st == 0 and w_rsi == 0:
            continue

        def dfn(df_, w_st=w_st, w_macd=w_macd, w_rsi=w_rsi,
                r_lo=r_lo, r_hi=r_hi, thr=thr):
            return _direction_for_config(df_, w_st, w_macd, w_rsi, r_lo, r_hi, thr)

        tr = _score(train_df, dfn, args.symbol, args.capital, args.sl_pct, args.tp_pct)
        te = _score(test_df,  dfn, args.symbol, args.capital, args.sl_pct, args.tp_pct)

        results.append({
            "w_st": w_st, "w_macd": w_macd, "w_rsi": w_rsi,
            "rsi_lo": r_lo, "rsi_hi": r_hi, "threshold": thr,
            "train_trades": tr["trades"], "train_wr": tr["win_rate"],
            "train_lb": tr["wilson_lb_95"], "train_sharpe": tr["sharpe"],
            "train_pf": tr["profit_factor"],
            "test_trades": te["trades"], "test_wr": te["win_rate"],
            "test_lb": te["wilson_lb_95"], "test_sharpe": te["sharpe"],
            "test_pf": te["profit_factor"],
        })

    # Robustness filter
    robust = [
        r for r in results
        if r["train_trades"] >= 20 and r["test_trades"] >= 10
        and r["train_lb"] > bt_train["wilson_lb_95"]
        and r["test_lb"]  > bt_test["wilson_lb_95"]
    ]
    print(f"\n{len(robust)} robust configs (out of {len(results)} valid)")
    print(f"  i.e. beat plain-MACD Wilson LB on BOTH train and test\n")

    # Rank by test_lb (out-of-sample is the truth)
    ranked = sorted(robust, key=lambda r: r["test_lb"], reverse=True)

    # Save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["w_st","w_macd","w_rsi","rsi_lo","rsi_hi","threshold",
            "train_trades","train_wr","train_lb","train_sharpe","train_pf",
            "test_trades","test_wr","test_lb","test_sharpe","test_pf"]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in ranked:
            w.writerow({k: r[k] for k in cols})
    print(f"Wrote {out_path}\n")

    if not ranked:
        print("WARNING: no config beat plain MACD on both train AND test.")
        print("Interpretation: the in-sample winners from sweep_combined_rule were")
        print("likely overfit. Plain MACD is a stronger baseline than it looked.")
        return

    print("=" * 112)
    print(f"TOP {args.top} ROBUST CONFIGS (sorted by TEST Wilson LB - out-of-sample)")
    print("=" * 112)
    print(f"{'#':<3}{'wST':>5}{'wMACD':>7}{'wRSI':>6}{'rsiLo':>7}{'rsiHi':>7}{'thr':>5}  "
          f"{'TR-Trd':>7}{'TR-LB':>7}{'TR-Shp':>8}{'TR-PF':>7}   "
          f"{'TE-Trd':>7}{'TE-LB':>7}{'TE-Shp':>8}{'TE-PF':>7}")
    for i, r in enumerate(ranked[:args.top], 1):
        print(f"{i:<3}{r['w_st']:>5}{r['w_macd']:>7}{r['w_rsi']:>6}{r['rsi_lo']:>7}"
              f"{r['rsi_hi']:>7}{r['threshold']:>5}  "
              f"{r['train_trades']:>7}{r['train_lb']*100:>6.1f}%{r['train_sharpe']:>8.2f}"
              f"{r['train_pf']:>7.2f}   "
              f"{r['test_trades']:>7}{r['test_lb']*100:>6.1f}%{r['test_sharpe']:>8.2f}"
              f"{r['test_pf']:>7.2f}")


if __name__ == "__main__":
    main()
