import yfinance as yf
import pandas as pd
import httpx
from datetime import datetime, time as dtime
import time

# In-memory cache: {key: (timestamp, data)}
_cache: dict = {}
CACHE_TTL = 10  # seconds — fast refresh for live chart

TICKERS = {
    "NIFTY":  "^NSEI",
    "SENSEX": "^BSESN",
}

LOT_SIZES = {
    "NIFTY":  25,
    "SENSEX": 20,
}

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

def _cache_get(key):
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
    return None

def _cache_set(key, data):
    _cache[key] = (time.time(), data)

def is_market_open() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    market_open  = dtime(9, 15)
    market_close = dtime(15, 30)
    return market_open <= now.time() <= market_close


def _fetch_yahoo_direct(symbol: str, interval: str) -> pd.DataFrame:
    """Direct Yahoo Finance API fetch — fallback when yfinance library is blocked."""
    range_map = {"1m": "1d", "2m": "5d", "5m": "5d", "15m": "60d"}
    yf_range = range_map.get(interval, "5d")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={yf_range}"

    resp = httpx.get(url, headers=_YF_HEADERS, timeout=10, follow_redirects=True)
    resp.raise_for_status()
    data = resp.json()

    result = data.get("chart", {}).get("result", [])
    if not result:
        raise ValueError("No chart data in Yahoo response")

    r = result[0]
    timestamps = r.get("timestamp", [])
    quote = r.get("indicators", {}).get("quote", [{}])[0]

    rows = []
    for i in range(len(timestamps)):
        o = quote.get("open", [None])[i] if i < len(quote.get("open", [])) else None
        h = quote.get("high", [None])[i] if i < len(quote.get("high", [])) else None
        lo = quote.get("low", [None])[i] if i < len(quote.get("low", [])) else None
        c = quote.get("close", [None])[i] if i < len(quote.get("close", [])) else None
        v = quote.get("volume", [0])[i] if i < len(quote.get("volume", [])) else 0
        if o is None or c is None:
            continue
        rows.append({
            "Open": round(o, 2), "High": round(h, 2), "Low": round(lo, 2),
            "Close": round(c, 2), "Volume": v or 0,
            "_ts": timestamps[i],
        })

    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["_ts"], unit="s")
    df = df.drop(columns=["_ts"])
    df.index.name = "Datetime"
    return df


def get_ohlcv(ticker: str, interval: str = "5m") -> pd.DataFrame:
    """
    Fetch OHLCV data for NIFTY or SENSEX.
    Tries yfinance first, falls back to direct Yahoo Finance API.
    """
    cache_key = f"ohlcv_{ticker}_{interval}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    symbol = TICKERS.get(ticker.upper(), ticker)
    period = "5d" if interval in ("1m", "2m", "5m") else "60d"

    # Try yfinance library first
    df = None
    try:
        df = yf.download(symbol, period=period, interval=interval,
                         progress=False, auto_adjust=True)
        if df.empty:
            df = None
        else:
            # yfinance >= 1.0 returns MultiIndex columns (Price, Ticker)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
    except Exception:
        df = None

    # Fallback: direct Yahoo Finance HTTP API
    if df is None or df.empty:
        df = _fetch_yahoo_direct(symbol, interval)

    if df.empty:
        raise ValueError(f"No data returned for {ticker}")

    df.index = pd.to_datetime(df.index)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    _cache_set(cache_key, df)
    return df

def get_spot_price(ticker: str) -> float:
    """Return the latest closing price for a ticker."""
    df = get_ohlcv(ticker, interval="5m")
    return float(df["Close"].iloc[-1])

def get_market_status() -> dict:
    from data.options_chain import get_next_expiry
    open_ = is_market_open()
    now = datetime.now()
    expiry = get_next_expiry("NIFTY")
    delta = expiry - now
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    mins = rem // 60
    return {
        "is_open": open_,
        "current_time": now.strftime("%H:%M:%S"),
        "next_expiry_nifty": expiry.strftime("%Y-%m-%d"),
        "time_to_expiry": f"{hours}h {mins}m",
    }
