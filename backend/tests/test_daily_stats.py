"""
TDD test suite for get_daily_candle_stats().

Tests cover:
  TC-1  Opening candle OHLC is correct (first 1m bar at 9:15 IST)
  TC-2  First-5-min high/low spans 9:15–9:19 (5 bars)
  TC-3  First-15-min high/low spans 9:15–9:29 (15 bars)
  TC-4  Day-so-far stats cover the full session
  TC-5  Returns {} when no data (NSE down + yfinance fails)
  TC-6  Pre-market candles are excluded from all aggregations
  TC-7  Partial session (only 3 candles available) still returns valid stats
  TC-8  SENSEX ticker is accepted and produces a valid result
"""

import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

IST = timezone(timedelta(hours=5, minutes=30))
MARKET_OPEN_IST = datetime(2026, 5, 10, 9, 15, 0, tzinfo=IST)


def make_candles(base_ist: datetime, price_tuples: list[tuple]) -> list[dict]:
    """Build 1m OHLCV candle list. base_ist must be timezone-aware IST datetime."""
    base_ts = int(base_ist.timestamp())
    candles = []
    for i, (o, h, lo, c) in enumerate(price_tuples):
        candles.append({
            "time": base_ts + i * 60,
            "open": float(o), "high": float(h),
            "low": float(lo), "close": float(c), "volume": 0,
        })
    return candles


# 16 synthetic candles: 9:15..9:30 IST
# indices 0-4  → 9:15-9:19  (first 5 min)
# indices 0-14 → 9:15-9:29  (first 15 min)
# indices 0-15 → 9:15-9:30  (day so far — 9:30 is still within session)
SAMPLE_PRICES = [
    (23500, 23520, 23490, 23510),  # 9:15 opening candle
    (23510, 23530, 23505, 23525),  # 9:16
    (23525, 23540, 23520, 23535),  # 9:17
    (23535, 23545, 23530, 23540),  # 9:18
    (23540, 23555, 23535, 23550),  # 9:19 — end of first 5 min
    (23550, 23560, 23545, 23555),  # 9:20
    (23555, 23565, 23548, 23558),  # 9:21
    (23558, 23570, 23550, 23560),  # 9:22
    (23560, 23575, 23555, 23568),  # 9:23
    (23568, 23580, 23560, 23572),  # 9:24
    (23572, 23585, 23565, 23578),  # 9:25
    (23578, 23590, 23570, 23582),  # 9:26
    (23582, 23595, 23575, 23588),  # 9:27
    (23588, 23600, 23580, 23592),  # 9:28
    (23592, 23610, 23585, 23605),  # 9:29 — end of first 15 min
    (23605, 23620, 23600, 23615),  # 9:30 — in session, beyond 15min window
]

# Pre-market candle that should always be excluded
PRE_MARKET = (23400, 23420, 23390, 23410)  # 9:14 IST


def _prev_close_df():
    """Minimal 2-row daily DataFrame so prev_close can be computed."""
    idx = pd.to_datetime(["2026-05-09", "2026-05-10"])
    return pd.DataFrame(
        {"Open": [23000, 23500], "High": [23600, 23700],
         "Low": [22900, 23400], "Close": [23450, 23615], "Volume": [0, 0]},
        index=idx,
    )


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the in-memory cache before every test to prevent cross-test pollution."""
    import data.market_data as md
    md._cache.clear()
    yield
    md._cache.clear()


# ── TC-1: Opening candle ───────────────────────────────────────────────────
def test_tc1_opening_candle_ohlc():
    candles = make_candles(MARKET_OPEN_IST, SAMPLE_PRICES)
    with patch("data.market_data._fetch_nse_chart", return_value=candles), \
         patch("data.market_data.get_ohlcv", return_value=_prev_close_df()):
        from data.market_data import get_daily_candle_stats
        result = get_daily_candle_stats("NIFTY")

    oc = result["opening_candle"]
    assert oc["open"]  == 23500.0
    assert oc["high"]  == 23520.0
    assert oc["low"]   == 23490.0
    assert oc["close"] == 23510.0


# ── TC-2: First 5 min (9:15–9:19, 5 bars) ─────────────────────────────────
def test_tc2_first_5min_high_low():
    candles = make_candles(MARKET_OPEN_IST, SAMPLE_PRICES)
    with patch("data.market_data._fetch_nse_chart", return_value=candles), \
         patch("data.market_data.get_ohlcv", return_value=_prev_close_df()):
        from data.market_data import get_daily_candle_stats
        result = get_daily_candle_stats("NIFTY")

    f5 = result["first_5min"]
    assert f5["high"] == 23555.0  # max of highs 9:15-9:19
    assert f5["low"]  == 23490.0  # min of lows  9:15-9:19
    assert f5["open"] == 23500.0  # open of first bar
    assert f5["close"] == 23550.0  # close of last bar in window


# ── TC-3: First 15 min (9:15–9:29, 15 bars) ───────────────────────────────
def test_tc3_first_15min_high_low():
    candles = make_candles(MARKET_OPEN_IST, SAMPLE_PRICES)
    with patch("data.market_data._fetch_nse_chart", return_value=candles), \
         patch("data.market_data.get_ohlcv", return_value=_prev_close_df()):
        from data.market_data import get_daily_candle_stats
        result = get_daily_candle_stats("NIFTY")

    f15 = result["first_15min"]
    assert f15["high"] == 23610.0  # max of highs 9:15-9:29
    assert f15["low"]  == 23490.0  # min of lows  9:15-9:29
    assert f15["open"] == 23500.0
    assert f15["close"] == 23605.0  # close of bar at 9:29


# ── TC-4: Day-so-far stats ─────────────────────────────────────────────────
def test_tc4_day_stats():
    candles = make_candles(MARKET_OPEN_IST, SAMPLE_PRICES)
    with patch("data.market_data._fetch_nse_chart", return_value=candles), \
         patch("data.market_data.get_ohlcv", return_value=_prev_close_df()):
        from data.market_data import get_daily_candle_stats
        result = get_daily_candle_stats("NIFTY")

    day = result["day"]
    assert day["open"]  == 23500.0
    assert day["high"]  == 23620.0  # includes 9:30 bar
    assert day["low"]   == 23490.0
    assert day["close"] == 23615.0
    assert day["prev_close"] == 23450.0
    assert day["change_pts"] == pytest.approx(165.0, abs=0.1)
    assert day["change_pct"] == pytest.approx(0.70, abs=0.1)


# ── TC-5: No data → empty dict ─────────────────────────────────────────────
def test_tc5_no_data_returns_empty_dict():
    with patch("data.market_data._fetch_nse_chart", return_value=[]), \
         patch("data.market_data.get_ohlcv", side_effect=Exception("no data")):
        from data.market_data import get_daily_candle_stats
        result = get_daily_candle_stats("NIFTY")
    assert result == {}


# ── TC-6: Pre-market candles excluded ─────────────────────────────────────
def test_tc6_pre_market_candles_excluded():
    # Prepend a 9:14 IST candle (1 min before market open)
    pre_ts = int(MARKET_OPEN_IST.timestamp()) - 60
    pre_candle = {"time": pre_ts, "open": 23400, "high": 23420, "low": 23390, "close": 23410, "volume": 0}
    candles = [pre_candle] + make_candles(MARKET_OPEN_IST, SAMPLE_PRICES[:5])

    with patch("data.market_data._fetch_nse_chart", return_value=candles), \
         patch("data.market_data.get_ohlcv", return_value=_prev_close_df()):
        from data.market_data import get_daily_candle_stats
        result = get_daily_candle_stats("NIFTY")

    # The pre-market 23420 high and 23390 low must NOT appear in any result
    assert result["opening_candle"]["high"] == 23520.0
    assert result["day"]["low"] != 23390.0
    assert result["day"]["open"] == 23500.0


# ── TC-7: Partial session (3 candles) ─────────────────────────────────────
def test_tc7_partial_session_still_valid():
    candles = make_candles(MARKET_OPEN_IST, SAMPLE_PRICES[:3])  # only 9:15-9:17
    with patch("data.market_data._fetch_nse_chart", return_value=candles), \
         patch("data.market_data.get_ohlcv", return_value=_prev_close_df()):
        from data.market_data import get_daily_candle_stats
        result = get_daily_candle_stats("NIFTY")

    assert result != {}
    assert result["opening_candle"]["open"] == 23500.0
    assert result["first_5min"] is not None   # partial 5-min window
    assert result["first_15min"] is not None
    assert result["day"]["high"] == 23540.0


# ── TC-8: SENSEX ticker accepted ──────────────────────────────────────────
def test_tc8_sensex_ticker_accepted():
    candles = make_candles(MARKET_OPEN_IST, SAMPLE_PRICES[:5])
    with patch("data.market_data._fetch_nse_chart", return_value=candles), \
         patch("data.market_data.get_ohlcv", return_value=_prev_close_df()):
        from data.market_data import get_daily_candle_stats
        result = get_daily_candle_stats("SENSEX")

    assert "opening_candle" in result
    assert "first_5min" in result
    assert "first_15min" in result
    assert "day" in result
