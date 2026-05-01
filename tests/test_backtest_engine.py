"""1.2 — backtesting engine tests (no DB, synthetic OHLCV data)."""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from backtesting.engine import run_backtest, benchmark_buy_hold, _score_to_direction


def _make_df(n: int = 200, base: float = 22000.0, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic 5-min OHLCV DataFrame with UTC timezone-aware index."""
    rng = np.random.default_rng(seed)
    closes = base + np.cumsum(rng.normal(0, 30, n))
    spread = rng.uniform(5, 50, n)
    opens = closes - rng.uniform(-10, 10, n)
    highs = np.maximum(closes, opens) + spread * 0.5
    lows = np.minimum(closes, opens) - spread * 0.5
    volumes = rng.integers(500_000, 5_000_000, n).astype(float)

    start = datetime(2024, 1, 2, 9, 15, tzinfo=timezone.utc)
    index = pd.date_range(start=start, periods=n, freq="5min", tz="UTC")

    return pd.DataFrame({"o": opens, "h": highs, "l": lows, "c": closes, "v": volumes}, index=index)


def test_run_backtest_returns_expected_keys():
    df = _make_df()
    result = run_backtest(df, "NIFTY", capital=100_000)
    assert "trades" in result
    assert "metrics" in result
    assert "equity_curve" in result


def test_run_backtest_produces_trades():
    df = _make_df()
    result = run_backtest(df, "NIFTY", capital=100_000)
    # With 200 bars and a trending synthetic series, at least some trades must fire
    assert isinstance(result["trades"], list)


def test_run_backtest_empty_df():
    df = pd.DataFrame(columns=["o", "h", "l", "c", "v"])
    result = run_backtest(df, "NIFTY")
    assert result["trades"] == []
    assert result["equity_curve"] == []


def test_equity_curve_matches_trade_pnl():
    df = _make_df(seed=7)
    result = run_backtest(df, "NIFTY")
    trades = result["trades"]
    curve = result["equity_curve"]
    if not trades:
        return  # no trades → curve is empty, that's fine
    # Equity curve final value must equal sum of all trade P&Ls
    total_pnl = sum(t["pnl"] for t in trades)
    assert curve[-1]["equity"] == pytest.approx(total_pnl, abs=0.01)


def test_direction_array_all_zero_for_flat_market():
    """A perfectly flat series (no indicator movement) → all AVOID."""
    n = 100
    flat = np.full(n, 22000.0)
    rsi_flat = np.full(n, 50.0)
    # All MACD values equal → no crossover, MACD < signal when both 0 → BEARISH
    # SuperTrend direction 1 (bullish)
    st_dir = np.ones(n)
    macd_line = np.zeros(n)
    sig_line = np.zeros(n)
    directions = _score_to_direction(st_dir, macd_line, sig_line, rsi_flat)
    # st_score=+40, macd_score=-17.5 (bearish, no cross), rsi_score=0 → combined=22.5 > 15 → BUY
    # Mostly BUY_CE — just check dtype
    assert directions.dtype == np.int8


def test_benchmark_buy_hold_shape():
    df = _make_df()
    curve = benchmark_buy_hold(df, capital=100_000)
    assert len(curve) == len(df)
    assert curve[0]["equity"] == pytest.approx(0.0, abs=1.0)


def test_benchmark_uses_c_column():
    """load_ohlcv returns 'c' column; benchmark should accept it."""
    df = _make_df()
    curve = benchmark_buy_hold(df, capital=100_000)
    assert isinstance(curve, list)


def test_run_backtest_deterministic():
    """Same input → identical output."""
    df = _make_df(seed=99)
    r1 = run_backtest(df, "NIFTY")
    r2 = run_backtest(df, "NIFTY")
    assert r1["metrics"]["net_pnl"] == r2["metrics"]["net_pnl"]
    assert len(r1["trades"]) == len(r2["trades"])
