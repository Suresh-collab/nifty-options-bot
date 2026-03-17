import yfinance as yf
import pandas as pd
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

def get_ohlcv(ticker: str, interval: str = "5m") -> pd.DataFrame:
    """
    Fetch OHLCV data for NIFTY or SENSEX.
    ticker: 'NIFTY' or 'SENSEX'
    interval: '5m' or '15m'
    """
    cache_key = f"ohlcv_{ticker}_{interval}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    symbol = TICKERS.get(ticker.upper(), ticker)
    period = "5d" if interval in ("1m", "2m", "5m") else "60d"
    df = yf.download(symbol, period=period, interval=interval,
                     progress=False, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")

    # yfinance >= 1.0 returns MultiIndex columns (Price, Ticker) — flatten them
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

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
