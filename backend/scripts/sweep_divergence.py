"""
Parameter sweep + confluence test for the divergence indicator.

Three scenarios per symbol:
  1. Sweep pivot_lookback / max_hold on 1d bars over 2y    (does any setting work?)
  2. Same sweep on 5m bars over 60d                         (intraday alternative)
  3. CONFLUENCE TEST: baseline signal AND divergence agrees (filter overlay)

Goal: find a configuration that has a real edge, or honestly conclude
that the divergence indicator should not be promoted yet.
"""

from __future__ import annotations

import os
import sys
import urllib.parse

import httpx
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.engine import _rsi, _macd, _supertrend          # noqa: E402
from indicators.divergence import detect_divergence             # noqa: E402
from backtesting.engine import (                                # noqa: E402
    LOT_SIZES, DELTA_FACTOR, _score_to_direction,
)
from backtesting.metrics import compute_all                     # noqa: E402
from backtesting.divergence_backtest import run_divergence_backtest, _atr  # noqa: E402

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def fetch(symbol: str, interval: str, yrange: str) -> pd.DataFrame:
    enc = urllib.parse.quote(symbol, safe="")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}"
           f"?interval={interval}&range={yrange}")
    try:
        resp = httpx.get(url, headers=_YF_HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  fetch error {symbol}/{interval}: {exc}")
        return pd.DataFrame()

    res = (data.get("chart") or {}).get("result") or []
    if not res:
        return pd.DataFrame()
    r = res[0]
    ts = r.get("timestamp") or []
    q = (r.get("indicators", {}).get("quote") or [{}])[0]
    adjc = (r.get("indicators", {}).get("adjclose") or [{}])
    adj = adjc[0].get("adjclose") if adjc else []
    rows = []
    for i, t in enumerate(ts):
        o = q.get("open",   [None])[i] if i < len(q.get("open",   [])) else None
        h = q.get("high",   [None])[i] if i < len(q.get("high",   [])) else None
        lo = q.get("low",    [None])[i] if i < len(q.get("low",    [])) else None
        c = (adj[i] if (adj and i < len(adj)) else None) \
            or (q.get("close",  [None])[i] if i < len(q.get("close",  [])) else None)
        v = q.get("volume", [0])[i] if i < len(q.get("volume", [])) else 0
        if o is None or c is None:
            continue
        rows.append({"o": float(o), "h": float(h or o), "l": float(lo or o),
                     "c": float(c), "v": float(v or 0), "_ts": t})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["_ts"], unit="s", utc=True)
    return df.drop(columns=["_ts"])[["o", "h", "l", "c", "v"]]


def confluence_backtest(df: pd.DataFrame, symbol: str,
                        capital: float = 100_000.0,
                        sl_atr: float = 1.5, tp_atr: float = 3.0,
                        max_hold: int = 20,
                        pivot_lookback: int = 5,
                        intraday_eod: bool = False) -> dict:
    """
    Confluence variant: trade only when baseline signal AND divergence agree
    on the same bar (or divergence within last `pivot_lookback*2` bars).
    """
    lot_size = LOT_SIZES.get(symbol, 25)
    df2 = df.rename(columns={"o": "Open", "h": "High", "l": "Low",
                             "c": "Close", "v": "Volume"})
    df2 = df2.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df2) < 60:
        return {"metrics": compute_all([]), "trades": []}

    close = df2["Close"]; high = df2["High"]; low = df2["Low"]
    rsi = _rsi(close, 14).values
    macd_line, signal_line, _ = _macd(close, 12, 26, 9)
    _, st_dir = _supertrend(high, low, close, 7, 3.0)
    base_dir = _score_to_direction(st_dir.values, macd_line.values,
                                   signal_line.values, rsi)
    div_sig, _ev = detect_divergence(close, rsi=pd.Series(rsi),
                                     pivot_lookback=pivot_lookback,
                                     max_lookback_bars=60)
    atr = _atr(high, low, close, 14).values

    # Confluence: divergence signal must have fired within the last `window` bars
    # AND match baseline direction
    window = pivot_lookback * 3
    closes = close.values
    timestamps = df2.index

    trades = []
    position = 0
    entry_idx = entry_price = entry_atr = 0
    lots = 1
    eod_offset = pd.Timedelta(hours=5, minutes=30)

    for i in range(60, len(df2)):
        is_eod = False
        if intraday_eod:
            ist = timestamps[i] + eod_offset
            is_eod = (ist.hour > 15) or (ist.hour == 15 and ist.minute >= 30)

        # exit
        if position != 0:
            held = i - entry_idx
            move = closes[i] - entry_price if position == 1 else entry_price - closes[i]
            sl_hit = move <= -sl_atr * entry_atr
            tp_hit = move >= tp_atr * entry_atr
            reversal = base_dir[i] == -position
            if sl_hit or tp_hit or reversal or held >= max_hold or is_eod:
                trades.append({
                    "entry_ts": timestamps[entry_idx].isoformat(),
                    "exit_ts":  timestamps[i].isoformat(),
                    "symbol":   symbol,
                    "direction": "BUY_CE" if position == 1 else "BUY_PE",
                    "entry_price": round(entry_price, 2),
                    "exit_price":  round(closes[i], 2),
                    "qty":         lots,
                    "pnl":         round(move * lot_size * lots * DELTA_FACTOR, 2),
                })
                position = 0

        # entry: confluence required
        if position == 0 and not is_eod:
            # Recent divergence signal of matching sign within window?
            lo = max(0, i - window)
            recent_div_window = div_sig[lo: i + 1]
            recent_bull = (recent_div_window == 1).any()
            recent_bear = (recent_div_window == -1).any()
            base = base_dir[i]
            if base == 1 and recent_bull and not np.isnan(atr[i]) and atr[i] > 0:
                position = 1
            elif base == -1 and recent_bear and not np.isnan(atr[i]) and atr[i] > 0:
                position = -1
            if position != 0:
                spot = closes[i]
                lots = max(1, int(capital / (spot * lot_size * DELTA_FACTOR)))
                entry_idx = i
                entry_price = spot
                entry_atr = float(atr[i])

    return {"metrics": compute_all(trades), "trades": trades}


def fmt(m: dict) -> str:
    return (f"trades={m['total_trades']:>4} "
            f"WR={m['win_rate']*100:>5.1f}% "
            f"PnL={m['net_pnl']:>+10,.0f} "
            f"PF={m['profit_factor']:>5.2f} "
            f"DD={m['max_drawdown']:>+8,.0f} "
            f"Sharpe={m['sharpe_ratio']:>+6.2f}")


def main() -> int:
    print("=" * 110)
    print("DIVERGENCE PARAMETER SWEEP + CONFLUENCE TEST")
    print("=" * 110)

    for yf_sym, sym in [("^NSEI", "NIFTY"), ("^NSEBANK", "BANKNIFTY")]:
        print(f"\n>>> {sym} <<<")

        # ---------- 1d sweep ----------
        df_d = fetch(yf_sym, "1d", "2y")
        if df_d.empty:
            print("  no daily data")
            continue
        print(f"  1d bars: {len(df_d)} ({df_d.index[0].date()} to {df_d.index[-1].date()})")
        print(f"  -- DIVERGENCE-ONLY (1d) — pivot_lookback sweep --")
        for pl in [3, 5, 8]:
            for mh in [5, 10, 20]:
                r = run_divergence_backtest(df_d, sym, capital=100_000,
                                            sl_atr_mult=1.5, tp_atr_mult=3.0,
                                            max_hold_bars=mh,
                                            pivot_lookback=pl)["metrics"]
                print(f"    pivot={pl} hold={mh:>2} ==> {fmt(r)}")

        print(f"  -- CONFLUENCE (1d) — baseline + divergence agreement --")
        r = confluence_backtest(df_d, sym, max_hold=20, pivot_lookback=5)["metrics"]
        print(f"    pivot=5 hold=20 ==> {fmt(r)}")

        # ---------- 5m sweep (intraday) ----------
        df_5m = fetch(yf_sym, "5m", "60d")
        if df_5m.empty:
            print("  no 5m data")
            continue
        print(f"\n  5m bars: {len(df_5m)}")
        print(f"  -- DIVERGENCE-ONLY (5m) — pivot_lookback sweep --")
        for pl in [3, 5, 8]:
            for mh in [12, 30, 60]:  # 1h, 2.5h, 5h max hold
                r = run_divergence_backtest(df_5m, sym, capital=100_000,
                                            sl_atr_mult=1.5, tp_atr_mult=3.0,
                                            max_hold_bars=mh,
                                            pivot_lookback=pl)["metrics"]
                print(f"    pivot={pl} hold={mh:>2} ==> {fmt(r)}")

        print(f"  -- CONFLUENCE (5m intraday-EOD) --")
        r = confluence_backtest(df_5m, sym, max_hold=30, pivot_lookback=5,
                                intraday_eod=True)["metrics"]
        print(f"    pivot=5 hold=30 EOD ==> {fmt(r)}")

    print("\n" + "=" * 110)
    return 0


if __name__ == "__main__":
    sys.exit(main())
