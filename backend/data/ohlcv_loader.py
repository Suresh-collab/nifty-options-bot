"""
OHLCV data loader — fetches from yfinance and upserts into ohlcv_cache (Postgres).

Intervals stored:
  5m  → 60 days   (yfinance hard limit for sub-hourly data)
  1d  → 2 years   (yfinance supports 10+ years for daily)

Symbols stored: NIFTY (^NSEI), BANKNIFTY (^NSEBANK)

Usage:
    import asyncio
    from data.ohlcv_loader import refresh_ohlcv
    asyncio.run(refresh_ohlcv())
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

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


class OHLCVRow(NamedTuple):
    symbol: str
    interval: str
    ts: datetime
    o: float
    h: float
    l: float
    c: float
    v: float


def _fetch(yf_ticker: str, interval: str, days: int) -> pd.DataFrame:
    """Fetch OHLCV from yfinance, return normalised DataFrame (may be empty)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
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
    except Exception as exc:
        logger.warning("yfinance download failed for %s/%s: %s", yf_ticker, interval, exc)
        return pd.DataFrame()

    if df.empty:
        logger.warning("yfinance returned empty DataFrame for %s/%s", yf_ticker, interval)
        return pd.DataFrame()

    # yfinance may return MultiIndex columns — flatten them
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"})
    df = df[["o", "h", "l", "c", "v"]].dropna(subset=["o", "c"])

    # Ensure timezone-aware UTC index
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

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

    # Build values list for executemany-style insert
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
    Returns a summary dict: {symbol/interval: rows_inserted}.
    """
    if symbols is None:
        symbols = _SYMBOLS

    factory = get_session_factory()
    summary: dict[str, int] = {}

    async with factory() as session:
        for yf_ticker, db_symbol in symbols:
            for interval, days in _INTERVALS:
                key = f"{db_symbol}/{interval}"
                logger.info("Fetching %s ...", key)
                df = _fetch(yf_ticker, interval, days)
                if df.empty:
                    summary[key] = 0
                    continue
                rows = _df_to_rows(df, db_symbol, interval)
                inserted = await _upsert_batch(session, rows)
                summary[key] = inserted
                logger.info("Upserted %d rows for %s", len(rows), key)

    return summary


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
    result = await session.execute(stmt, {"symbol": symbol, "interval": interval, "start": start, "end": end})
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame(columns=["o", "h", "l", "c", "v"])

    df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    return df
