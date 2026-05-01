"""
OHLCV data loader — fetches from yfinance (with direct httpx fallback) and
upserts into ohlcv_cache (Postgres).

Intervals stored:
  5m  → 60 days   (yfinance hard limit for sub-hourly data)
  1d  → 2 years   (yfinance supports 10+ years for daily)

Symbols stored: NIFTY (^NSEI), BANKNIFTY (^NSEBANK)
"""

import logging
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import httpx
import pandas as pd
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import get_session_factory

logger = logging.getLogger(__name__)

# (yfinance ticker, display symbol stored in DB)
_SYMBOLS: list[tuple[str, str]] = [
    ("^NSEI", "NIFTY"),
    ("^NSEBANK", "BANKNIFTY"),
]

# (interval, lookback in calendar days)
_INTERVALS: list[tuple[str, int]] = [
    ("5m", 59),   # yfinance limit is 60 days; use 59 to stay safe
    ("1d", 730),  # 2 years of daily candles
]

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Yahoo Finance range strings for each interval
_RANGE_MAP: dict[str, str] = {
    "5m":  "60d",
    "15m": "60d",
    "1h":  "730d",
    "1d":  "2y",
}


class OHLCVRow(NamedTuple):
    symbol: str
    interval: str
    ts: datetime
    o: float
    h: float
    l: float
    c: float
    v: float


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns, rename to o/h/l/c/v, ensure UTC index."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"})
    # Keep only OHLCV columns that exist
    cols = [c for c in ["o", "h", "l", "c", "v"] if c in df.columns]
    df = df[cols].dropna(subset=["o", "c"])
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    return df


def _fetch_direct(yf_ticker: str, interval: str) -> pd.DataFrame:
    """
    Fallback: call Yahoo Finance v8 chart API directly via httpx.
    Mirrors the pattern used in market_data._fetch_yahoo_direct().
    """
    yf_range = _RANGE_MAP.get(interval, "60d")
    ticker_enc = urllib.parse.quote(yf_ticker, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_enc}"
        f"?interval={interval}&range={yf_range}"
    )

    try:
        resp = httpx.get(url, headers=_YF_HEADERS, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("Direct Yahoo API request failed for %s/%s: %s", yf_ticker, interval, exc)
        return pd.DataFrame()

    chart = data.get("chart", {})
    result = chart.get("result") or []
    if not result:
        err = chart.get("error") or {}
        logger.error(
            "No chart result for %s/%s — Yahoo error: %s",
            yf_ticker, interval, err.get("description", err)
        )
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
        o  = opens[i]   if i < len(opens)   else None
        h  = highs[i]   if i < len(highs)   else None
        lo = lows[i]    if i < len(lows)    else None
        # prefer adjusted close; fall back to close
        c  = (adjclose[i] if (adjclose and i < len(adjclose)) else None) \
             or (closes[i] if i < len(closes) else None)
        v  = volumes[i] if i < len(volumes) else 0
        if o is None or c is None:
            continue
        rows.append({
            "o": float(o),
            "h": float(h if h is not None else o),
            "l": float(lo if lo is not None else o),
            "c": float(c),
            "v": float(v or 0),
            "_ts": ts,
        })

    if not rows:
        logger.error("Parsed 0 rows from direct Yahoo API for %s/%s", yf_ticker, interval)
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["_ts"], unit="s", utc=True)
    df.index.name = "Datetime"
    df = df.drop(columns=["_ts"])
    return df[["o", "h", "l", "c", "v"]].dropna(subset=["o", "c"])


def _fetch(yf_ticker: str, interval: str, days: int) -> pd.DataFrame:
    """
    Fetch OHLCV for (yf_ticker, interval).
    Strategy: try yfinance library → fall back to direct Yahoo Finance API.
    """
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    # --- attempt 1: yfinance library ---
    try:
        df = yf.download(
            yf_ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=interval,
            progress=False,
            auto_adjust=True,
            threads=False,
        )
        if not df.empty:
            df = _normalize_df(df)
            if not df.empty:
                logger.info(
                    "yfinance returned %d rows for %s/%s", len(df), yf_ticker, interval
                )
                return df
        logger.warning(
            "yfinance returned empty data for %s/%s — falling back to direct API",
            yf_ticker, interval,
        )
    except Exception as exc:
        logger.warning(
            "yfinance failed for %s/%s: %s — falling back to direct API",
            yf_ticker, interval, exc,
        )

    # --- attempt 2: direct Yahoo Finance API ---
    logger.info("Trying direct Yahoo Finance API for %s/%s", yf_ticker, interval)
    df = _fetch_direct(yf_ticker, interval)
    if not df.empty:
        logger.info(
            "Direct API returned %d rows for %s/%s", len(df), yf_ticker, interval
        )
    else:
        logger.error("Both fetch methods returned empty data for %s/%s", yf_ticker, interval)
    return df


def _df_to_rows(df: pd.DataFrame, symbol: str, interval: str) -> list[OHLCVRow]:
    rows = []
    for ts, row in df.iterrows():
        rows.append(OHLCVRow(
            symbol=symbol,
            interval=interval,
            ts=ts.to_pydatetime(),
            o=float(row["o"]),
            h=float(row["h"]),
            l=float(row["l"]),
            c=float(row["c"]),
            v=float(row["v"]),
        ))
    return rows


async def _upsert_batch(session: AsyncSession, rows: list[OHLCVRow]) -> int:
    """Upsert rows using Postgres INSERT ... ON CONFLICT DO NOTHING."""
    if not rows:
        return 0
    stmt = text(
        "INSERT INTO ohlcv_cache (symbol, interval, ts, o, h, l, c, v) "
        "VALUES (:symbol, :interval, :ts, :o, :h, :l, :c, :v) "
        "ON CONFLICT (symbol, interval, ts) DO NOTHING"
    )
    params = [r._asdict() for r in rows]
    result = await session.execute(stmt, params)
    await session.commit()
    return result.rowcount if result.rowcount >= 0 else len(rows)


async def refresh_ohlcv(symbols: list[tuple[str, str]] | None = None) -> dict:
    """
    Fetch latest OHLCV data for all symbols/intervals and upsert into DB.
    Returns summary dict: {symbol/interval: rows_fetched} plus an 'errors' key
    if any symbol/interval failed.
    """
    if symbols is None:
        symbols = _SYMBOLS

    factory = get_session_factory()
    summary: dict[str, int] = {}
    errors: dict[str, str] = {}

    async with factory() as session:
        for yf_ticker, db_symbol in symbols:
            for interval, days in _INTERVALS:
                key = f"{db_symbol}/{interval}"
                logger.info("Fetching %s ...", key)
                df = _fetch(yf_ticker, interval, days)
                if df.empty:
                    errors[key] = "no data returned by yfinance or direct API"
                    summary[key] = 0
                    continue
                rows = _df_to_rows(df, db_symbol, interval)
                try:
                    inserted = await _upsert_batch(session, rows)
                    summary[key] = inserted if inserted > 0 else len(rows)
                    logger.info("Upserted %d rows for %s", summary[key], key)
                except Exception as exc:
                    logger.error("DB upsert failed for %s: %s", key, exc)
                    errors[key] = f"db error: {exc}"
                    summary[key] = 0

    result: dict = {"summary": summary}
    if errors:
        result["errors"] = errors
    return result


async def load_ohlcv(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    session: AsyncSession,
) -> pd.DataFrame:
    """
    Load OHLCV rows from DB for a given symbol/interval/date range.
    Returns a DataFrame indexed by UTC datetime with columns o, h, l, c, v.
    """
    stmt = text(
        "SELECT ts, o, h, l, c, v FROM ohlcv_cache "
        "WHERE symbol = :symbol AND interval = :interval "
        "  AND ts >= :start AND ts < :end "
        "ORDER BY ts ASC"
    )
    result = await session.execute(
        stmt, {"symbol": symbol, "interval": interval, "start": start, "end": end}
    )
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame(columns=["o", "h", "l", "c", "v"])

    df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df
