"""
Phase 6.2 — Market scanner for Nifty 50 stocks.
Uses yfinance batch download (single HTTP call) to stay under 10 s.
Results are cached for 5 minutes; POST /scanner/run invalidates the cache.
"""
import asyncio
import time
from datetime import datetime
from typing import Dict, List

_NIFTY50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "BHARTIARTL.NS", "ICICIBANK.NS",
    "INFOSYS.NS", "SBIN.NS", "HINDUNILVR.NS", "ITC.NS", "LT.NS",
    "KOTAKBANK.NS", "HCLTECH.NS", "BAJFINANCE.NS", "AXISBANK.NS", "WIPRO.NS",
    "NTPC.NS", "ONGC.NS", "POWERGRID.NS", "ULTRACEMCO.NS", "SUNPHARMA.NS",
    "MARUTI.NS", "TITAN.NS", "TATAMOTORS.NS", "NESTLEIND.NS", "ADANIENT.NS",
    "JSWSTEEL.NS", "TECHM.NS", "COALINDIA.NS", "BAJAJFINSV.NS", "GRASIM.NS",
    "ASIANPAINT.NS", "INDUSINDBK.NS", "HINDALCO.NS", "TATASTEEL.NS", "DRREDDY.NS",
    "CIPLA.NS", "BPCL.NS", "EICHERMOT.NS", "TATACONSUM.NS", "HEROMOTOCO.NS",
    "APOLLOHOSP.NS", "LTIM.NS", "DIVISLAB.NS", "M%26M.NS", "BAJAJ-AUTO.NS",
    "BRITANNIA.NS", "SBILIFE.NS", "HDFCLIFE.NS", "SHRIRAMFIN.NS", "ADANIPORTS.NS",
]

_cache: Dict = {"results": None, "updated_at": None}
_CACHE_TTL = 300  # 5 minutes


def _is_fresh() -> bool:
    return _cache["updated_at"] is not None and (time.time() - _cache["updated_at"]) < _CACHE_TTL


def _record(ticker: str, df) -> Dict:
    curr_close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])
    curr_vol   = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0
    avg_vol_5d = float(df["Volume"].iloc[-6:-1].mean()) if len(df) >= 6 and "Volume" in df.columns else curr_vol or 1
    high_20d   = float(df["High"].iloc[-21:-1].max()) if len(df) >= 21 else float(df["High"].max())
    low_20d    = float(df["Low"].iloc[-21:-1].min()) if len(df) >= 21 else float(df["Low"].min())

    chg_pct   = round((curr_close - prev_close) / prev_close * 100, 2) if prev_close else 0.0
    vol_ratio = round(curr_vol / avg_vol_5d, 2) if avg_vol_5d > 0 else 1.0

    return {
        "symbol":       ticker.replace(".NS", "").replace("%26", "&"),
        "close":        round(curr_close, 2),
        "change_pct":   chg_pct,
        "volume":       int(curr_vol),
        "vol_ratio":    vol_ratio,
        "high_20d":     round(high_20d, 2),
        "low_20d":      round(low_20d, 2),
        "breakout":     curr_close >= high_20d * 0.99,
        "breakdown":    curr_close <= low_20d * 1.01,
        "volume_spike": vol_ratio >= 2.0,
    }


def run_scan() -> Dict:
    if _is_fresh():
        return _cache["results"]

    try:
        import yfinance as yf

        data = yf.download(
            " ".join(_NIFTY50),
            period="25d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        results: List[Dict] = []
        top_lvl = data.columns.get_level_values(0)
        for ticker in _NIFTY50:
            try:
                if ticker not in top_lvl:
                    continue
                df = data[ticker].dropna(subset=["Close"])
                if len(df) < 2:
                    continue
                results.append(_record(ticker, df))
            except Exception:
                continue

        gainers    = sorted([r for r in results if r["change_pct"] > 0],  key=lambda x: x["change_pct"],  reverse=True)[:10]
        losers     = sorted([r for r in results if r["change_pct"] < 0],  key=lambda x: x["change_pct"])[:10]
        vol_spikes = sorted([r for r in results if r["volume_spike"]],    key=lambda x: x["vol_ratio"],    reverse=True)[:10]
        breakouts  = [r for r in results if r["breakout"] or r["breakdown"]]

        output: Dict = {
            "gainers":       gainers,
            "losers":        losers,
            "volume_spikes": vol_spikes,
            "breakouts":     breakouts,
            "total_scanned": len(results),
            "scanned_at":    datetime.now().isoformat(),
        }
        _cache["results"]    = output
        _cache["updated_at"] = time.time()
        return output

    except Exception as exc:
        return {
            "gainers": [], "losers": [], "volume_spikes": [], "breakouts": [],
            "total_scanned": 0, "scanned_at": datetime.now().isoformat(), "error": str(exc),
        }


def invalidate_cache() -> None:
    _cache["updated_at"] = None


async def run_scan_async() -> Dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, run_scan)
