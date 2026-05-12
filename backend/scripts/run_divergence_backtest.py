"""
Compare RSI-divergence strategy vs the existing baseline rule engine on
NIFTY and BANKNIFTY daily bars over the last 2 years.

Usage:
    cd backend && python scripts/run_divergence_backtest.py

Fetches data directly from yfinance — no DB required. Prints a side-by-side
metrics table for: BUY_HOLD, BASELINE (current signal engine), DIVERGENCE.

Used to validate whether RSI divergence as a standalone leading indicator
beats the current trend-following baseline before wiring it into the signal
engine.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import os
import urllib.parse

import httpx
import pandas as pd

# Make `backend/` the import root so the existing modules resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.engine import run_backtest, benchmark_buy_hold      # noqa: E402
from backtesting.divergence_backtest import run_divergence_backtest  # noqa: E402

SYMBOLS = [("^NSEI", "NIFTY"), ("^NSEBANK", "BANKNIFTY")]
CAPITAL = 100_000.0
INTERVAL = "1d"
DAYS = 730   # 2 years of daily bars

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def fetch(symbol: str) -> pd.DataFrame:
    """
    Direct Yahoo Finance v8 chart API — mirrors ohlcv_loader._fetch_direct().
    Bypasses the yfinance library which is currently being blocked.
    """
    enc = urllib.parse.quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}"
        f"?interval={INTERVAL}&range=2y"
    )
    try:
        resp = httpx.get(url, headers=_YF_HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  [fetch error] {symbol}: {exc}")
        return pd.DataFrame()

    result = (data.get("chart") or {}).get("result") or []
    if not result:
        err = (data.get("chart") or {}).get("error") or {}
        print(f"  [fetch empty] {symbol}: {err}")
        return pd.DataFrame()

    r = result[0]
    timestamps = r.get("timestamp") or []
    quote = (r.get("indicators", {}).get("quote") or [{}])[0]
    adjclose_data = r.get("indicators", {}).get("adjclose") or []
    adjclose = (adjclose_data[0].get("adjclose") or []) if adjclose_data else []

    opens   = quote.get("open",   [])
    highs   = quote.get("high",   [])
    lows    = quote.get("low",    [])
    closes  = quote.get("close",  [])
    volumes = quote.get("volume", [])

    rows = []
    for i, ts in enumerate(timestamps):
        o  = opens[i]  if i < len(opens)  else None
        h  = highs[i]  if i < len(highs)  else None
        lo = lows[i]   if i < len(lows)   else None
        c  = (adjclose[i] if (adjclose and i < len(adjclose)) else None) \
             or (closes[i] if i < len(closes) else None)
        v  = volumes[i] if i < len(volumes) else 0
        if o is None or c is None:
            continue
        rows.append({"o": float(o), "h": float(h if h is not None else o),
                     "l": float(lo if lo is not None else o),
                     "c": float(c), "v": float(v or 0), "_ts": ts})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["_ts"], unit="s", utc=True)
    df = df.drop(columns=["_ts"])
    return df[["o", "h", "l", "c", "v"]]


def buy_hold_metrics(df: pd.DataFrame, symbol: str) -> dict:
    """Return a metrics-like dict for buy-and-hold so it slots into the table."""
    if df.empty:
        return {"total_trades": 0, "win_rate": 0, "net_pnl": 0,
                "profit_factor": 0, "expectancy": 0, "max_drawdown": 0,
                "sharpe_ratio": 0}
    curve = benchmark_buy_hold(df, capital=CAPITAL)
    final = curve[-1]["equity"] if curve else 0.0
    # Max drawdown from the equity curve
    peak = 0.0
    max_dd = 0.0
    for pt in curve:
        eq = pt["equity"]
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
    return {
        "total_trades": 1,
        "win_rate":      1.0 if final > 0 else 0.0,
        "net_pnl":       round(final, 2),
        "profit_factor": float("inf") if final > 0 else 0.0,
        "expectancy":    round(final, 2),
        "max_drawdown":  round(max_dd, 2),
        "sharpe_ratio":  0.0,
    }


def format_row(label: str, m: dict) -> str:
    return (
        f"  {label:<18}"
        f"{m['total_trades']:>10}"
        f"{m['win_rate']*100:>10.1f}%"
        f"{m['net_pnl']:>16,.0f}"
        f"{m['profit_factor']:>10.2f}"
        f"{m['expectancy']:>14.0f}"
        f"{m['max_drawdown']:>14,.0f}"
        f"{m['sharpe_ratio']:>10.2f}"
    )


def header() -> str:
    return (
        f"  {'Strategy':<18}{'Trades':>10}{'WinRate':>11}"
        f"{'NetPnL (INR)':>16}{'PF':>10}{'Expectancy':>14}"
        f"{'MaxDD':>14}{'Sharpe':>10}"
    )


def main() -> int:
    print(f"\nDivergence vs Baseline backtest "
          f"(capital=INR {CAPITAL:,.0f}, "
          f"interval={INTERVAL}, lookback={DAYS}d)")
    print("=" * 110)

    all_results: dict[str, dict[str, dict]] = {}

    for yf_sym, display in SYMBOLS:
        print(f"\nFetching {display} ({yf_sym}) ...")
        df = fetch(yf_sym)
        if df.empty:
            print(f"  [skip] no data returned for {yf_sym}")
            continue
        print(f"  Got {len(df)} bars from "
              f"{df.index[0].strftime('%Y-%m-%d')} to "
              f"{df.index[-1].strftime('%Y-%m-%d')}")

        bh_m = buy_hold_metrics(df, display)
        base_m = run_backtest(df, display, capital=CAPITAL,
                              sl_pct=0.01, tp_pct=0.02)["metrics"]
        div_m = run_divergence_backtest(df, display, capital=CAPITAL,
                                        sl_atr_mult=1.5, tp_atr_mult=3.0,
                                        max_hold_bars=10)["metrics"]

        all_results[display] = {"BUY_HOLD": bh_m, "BASELINE": base_m, "DIVERGENCE": div_m}

        print(f"\n  {display} — daily bars")
        print(header())
        print("  " + "-" * 100)
        print(format_row("BUY_HOLD",     bh_m))
        print(format_row("BASELINE",     base_m))
        print(format_row("DIVERGENCE",   div_m))

    # --- combined verdict ---
    if not all_results:
        print("\nNo data fetched. yfinance may be rate-limited; retry later.")
        return 1

    print("\n" + "=" * 110)
    print("VERDICT")
    print("-" * 110)
    for sym, results in all_results.items():
        base_pnl = results["BASELINE"]["net_pnl"]
        div_pnl  = results["DIVERGENCE"]["net_pnl"]
        base_wr  = results["BASELINE"]["win_rate"]
        div_wr   = results["DIVERGENCE"]["win_rate"]
        base_pf  = results["BASELINE"]["profit_factor"]
        div_pf   = results["DIVERGENCE"]["profit_factor"]
        winner_pnl = "DIVERGENCE" if div_pnl > base_pnl else "BASELINE"
        winner_wr = "DIVERGENCE" if div_wr > base_wr else "BASELINE"
        print(
            f"  {sym}: "
            f"PnL winner = {winner_pnl} ({div_pnl:+,.0f} vs {base_pnl:+,.0f}) | "
            f"WR winner = {winner_wr} ({div_wr*100:.1f}% vs {base_wr*100:.1f}%) | "
            f"PF: div={div_pf:.2f} base={base_pf:.2f}"
        )
    print("=" * 110 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
