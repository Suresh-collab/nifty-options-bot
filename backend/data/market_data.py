import yfinance as yf
import pandas as pd
import httpx
from datetime import datetime, time as dtime, timezone, timedelta
import time

# IST timezone: UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

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
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    market_open  = dtime(9, 15)
    market_close = dtime(15, 30)
    return market_open <= now.time().replace(tzinfo=None) <= market_close


def _fetch_yahoo_direct(symbol: str, interval: str) -> pd.DataFrame:
    """Direct Yahoo Finance API fetch — fallback when yfinance library is blocked."""
    range_map = {"1m": "1d", "2m": "5d", "5m": "5d", "15m": "60d", "1d": "2y"}
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


NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

NSE_CHART_INDEXES = {
    "NIFTY":  "NIFTY 50",
    "SENSEX": "SENSEX",
}


def _fetch_nse_chart(ticker: str, interval: str = "5m") -> list:
    """
    Fetch intraday chart data from NSE India and aggregate into OHLCV candles.
    NSE returns ~1-min resolution [timestamp_ms, price] pairs for the current day.
    We aggregate these into candles of the requested interval.
    Returns list of dicts: [{time, open, high, low, close, volume}, ...]
    """
    index_name = NSE_CHART_INDEXES.get(ticker.upper())
    if not index_name:
        return []

    url = f"https://www.nseindia.com/api/chart-databyindex?index={index_name}&indices=true"

    try:
        with httpx.Client(headers=NSE_HEADERS, timeout=8, follow_redirects=True) as client:
            # NSE requires a session cookie — hit homepage first
            client.get("https://www.nseindia.com", timeout=5)
            resp = client.get(url, timeout=5)
            resp.raise_for_status()
            raw = resp.json()
    except Exception:
        return []

    # NSE response: {"gpiData": [[timestamp_ms, price], ...]}
    data_points = raw.get("gpiData", [])
    if not data_points or len(data_points) < 2:
        return []

    # Parse interval to seconds
    interval_map = {"1m": 60, "5m": 300, "15m": 900}
    bucket_secs = interval_map.get(interval, 300)

    # Group data points into candle buckets
    candles = []
    bucket_start = None
    bucket_prices = []

    for point in data_points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        ts_ms, price = point[0], point[1]
        if price is None or price == 0:
            continue

        ts_sec = int(ts_ms / 1000)
        bucket = (ts_sec // bucket_secs) * bucket_secs

        if bucket_start is None:
            bucket_start = bucket
            bucket_prices = [price]
        elif bucket == bucket_start:
            bucket_prices.append(price)
        else:
            # Close the previous bucket
            candles.append({
                "time": bucket_start,
                "open": round(bucket_prices[0], 2),
                "high": round(max(bucket_prices), 2),
                "low": round(min(bucket_prices), 2),
                "close": round(bucket_prices[-1], 2),
                "volume": 0,  # NSE chart API doesn't provide volume
            })
            bucket_start = bucket
            bucket_prices = [price]

    # Don't forget the last (forming) bucket
    if bucket_prices:
        candles.append({
            "time": bucket_start,
            "open": round(bucket_prices[0], 2),
            "high": round(max(bucket_prices), 2),
            "low": round(min(bucket_prices), 2),
            "close": round(bucket_prices[-1], 2),
            "volume": 0,
        })

    return candles


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

def get_daily_candle_stats(ticker: str) -> dict:
    """
    Compute daily range milestones from today's 1m intraday data.

    Returns a dict with four keys:
      opening_candle  — OHLC of the single 9:15 bar
      first_5min      — aggregated H/L/O/C for 9:15–9:19 (5 bars)
      first_15min     — aggregated H/L/O/C for 9:15–9:29 (15 bars)
      day             — full-session H/L/O/C + change vs prev close

    Returns {} when no intraday data is available (pre-market or data outage).
    """
    cache_key = f"daily_stats_{ticker}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # 1. Try NSE real-time 1m feed (today only, blocks non-Indian IPs gracefully)
    candles = _fetch_nse_chart(ticker, "1m")

    # 2. Fallback: yfinance 1m, filtered to today
    if not candles:
        try:
            df = get_ohlcv(ticker, "1m")
            today = datetime.now(IST).date()
            today_df = df[pd.to_datetime(df.index).tz_localize(None).date == today] \
                if df.index.tz is None \
                else df[df.index.tz_convert(IST).date == today]
            if not today_df.empty:
                candles = [
                    {
                        "time": int(row.Index.timestamp()),
                        "open": round(float(row.Open), 2),
                        "high": round(float(row.High), 2),
                        "low": round(float(row.Low), 2),
                        "close": round(float(row.Close), 2),
                        "volume": 0,
                    }
                    for row in today_df.itertuples()
                ]
        except Exception:
            pass

    if not candles:
        return {}

    def _ist_minute(ts: int) -> int:
        """Minutes since IST midnight for a UTC Unix timestamp."""
        return ((ts + 19800) % 86400) // 60

    # Market session: 9:15 (minute 555) to 15:30 (minute 930), exclusive of 930
    session = [c for c in candles if 555 <= _ist_minute(c["time"]) < 930]
    if not session:
        return {}

    def _r(v) -> float:
        return round(float(v), 2)

    def _agg(bars: list) -> dict | None:
        if not bars:
            return None
        return {
            "open":  _r(bars[0]["open"]),
            "high":  _r(max(b["high"] for b in bars)),
            "low":   _r(min(b["low"]  for b in bars)),
            "close": _r(bars[-1]["close"]),
        }

    opening_candle = _agg([session[0]])
    first_5min     = _agg([c for c in session if 555 <= _ist_minute(c["time"]) < 560])
    first_15min    = _agg([c for c in session if 555 <= _ist_minute(c["time"]) < 570])

    day_open  = _r(session[0]["open"])
    day_high  = _r(max(c["high"]  for c in session))
    day_low   = _r(min(c["low"]   for c in session))
    day_close = _r(session[-1]["close"])

    # Previous close for change calculation
    prev_close = change_pts = change_pct = None
    try:
        df_d = get_ohlcv(ticker, "1d")
        if len(df_d) >= 2:
            prev_close  = _r(float(df_d["Close"].iloc[-2]))
            change_pts  = _r(day_close - prev_close)
            change_pct  = _r((day_close - prev_close) / prev_close * 100)
    except Exception:
        pass

    result = {
        "ticker": ticker,
        "opening_candle": opening_candle,
        "first_5min": first_5min,
        "first_15min": first_15min,
        "day": {
            "open":       day_open,
            "high":       day_high,
            "low":        day_low,
            "close":      day_close,
            "prev_close": prev_close,
            "change_pts": change_pts,
            "change_pct": change_pct,
        },
        "candle_count": len(session),
    }
    _cache_set(cache_key, result)
    return result


def get_spot_price(ticker: str) -> float:
    """Return the latest closing price for a ticker."""
    df = get_ohlcv(ticker, interval="5m")
    return float(df["Close"].iloc[-1])

def get_market_status() -> dict:
    from data.options_chain import get_next_expiry
    open_ = is_market_open()
    now = datetime.now(IST)
    expiry = get_next_expiry("NIFTY")
    # Make expiry timezone-aware for correct delta calculation
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=IST)
    delta = expiry - now
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    mins = rem // 60
    return {
        "is_open": open_,
        "current_time": now.strftime("%H:%M:%S"),
        "next_expiry_nifty": expiry.strftime("%Y-%m-%d"),
        "time_to_expiry": f"{hours}h {mins}m",
    }
