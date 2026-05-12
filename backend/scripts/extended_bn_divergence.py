"""
Extended out-of-sample test: divergence-only on BANKNIFTY across longer
historical windows. The 2y sweep flagged pivot=3 hold=10 as promising
(7 trades, 71% WR, +37k PnL). Validate on 5y and on disjoint sub-periods.
"""
from __future__ import annotations

import os
import sys
import urllib.parse

import httpx
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtesting.divergence_backtest import run_divergence_backtest  # noqa: E402

_HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch(symbol: str, yrange: str = "5y") -> pd.DataFrame:
    enc = urllib.parse.quote(symbol, safe="")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}"
           f"?interval=1d&range={yrange}")
    resp = httpx.get(url, headers=_HDR, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    data = resp.json()
    r = data["chart"]["result"][0]
    ts = r["timestamp"]
    q = r["indicators"]["quote"][0]
    adj_block = r["indicators"].get("adjclose") or []
    adj = adj_block[0]["adjclose"] if adj_block else []
    rows = []
    for i, t in enumerate(ts):
        o = q["open"][i]; h = q["high"][i]; lo = q["low"][i]
        c = (adj[i] if (adj and i < len(adj)) else None) or q["close"][i]
        v = q["volume"][i] or 0
        if o is None or c is None:
            continue
        rows.append({"o": float(o), "h": float(h or o), "l": float(lo or o),
                     "c": float(c), "v": float(v), "_ts": t})
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["_ts"], unit="s", utc=True)
    return df.drop(columns=["_ts"])[["o", "h", "l", "c", "v"]]


def fmt(m):
    return (f"trades={m['total_trades']:>4} WR={m['win_rate']*100:>5.1f}% "
            f"PnL={m['net_pnl']:>+10,.0f} PF={m['profit_factor']:>5.2f} "
            f"DD={m['max_drawdown']:>+10,.0f} Sharpe={m['sharpe_ratio']:>+6.2f}")


def main() -> int:
    df = fetch("^NSEBANK", "5y")
    print(f"BANKNIFTY 5y daily: {len(df)} bars "
          f"({df.index[0].date()} to {df.index[-1].date()})")

    # --- best 2y setting on full 5y ---
    print("\nBest 2y setting (pivot=3 hold=10, ATR 1.5/3.0) on full 5y window:")
    print("  " + fmt(run_divergence_backtest(df, "BANKNIFTY",
                                             pivot_lookback=3, max_hold_bars=10)["metrics"]))

    # --- sweep again on 5y ---
    print("\nFull sweep on 5y window:")
    for pl in [3, 5, 8]:
        for mh in [5, 10, 20]:
            m = run_divergence_backtest(df, "BANKNIFTY",
                                        pivot_lookback=pl, max_hold_bars=mh)["metrics"]
            print(f"  pivot={pl} hold={mh:>2} ==> {fmt(m)}")

    # --- out-of-sample splits ---
    print("\nSplit 5y into two halves (out-of-sample test):")
    mid = len(df) // 2
    splits = [("first half", df.iloc[:mid]), ("second half", df.iloc[mid:])]
    for label, sub in splits:
        print(f"  {label} ({sub.index[0].date()} to {sub.index[-1].date()}, {len(sub)} bars)")
        for pl, mh in [(3, 10), (8, 20)]:
            m = run_divergence_backtest(sub, "BANKNIFTY",
                                        pivot_lookback=pl, max_hold_bars=mh)["metrics"]
            print(f"    pivot={pl} hold={mh} ==> {fmt(m)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
