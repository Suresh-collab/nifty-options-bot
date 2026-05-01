"""1.4 — backtest API endpoint integration tests."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
import pandas as pd
import numpy as np

from main import app


def _mock_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    closes = 22000.0 + np.cumsum(rng.normal(0, 30, n))
    spread = rng.uniform(5, 50, n)
    opens = closes - rng.uniform(-10, 10, n)
    highs = np.maximum(closes, opens) + spread * 0.5
    lows = np.minimum(closes, opens) - spread * 0.5
    volumes = rng.integers(500_000, 5_000_000, n).astype(float)
    index = pd.date_range("2024-01-02 09:15", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({"o": opens, "h": highs, "l": lows, "c": closes, "v": volumes}, index=index)


@pytest.mark.asyncio
async def test_create_backtest_invalid_symbol():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/backtest", json={
            "symbol": "SENSEX",
            "start_date": "2024-01-01",
            "end_date": "2024-03-01",
            "capital": 100000,
        })
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_create_backtest_invalid_dates():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/backtest", json={
            "symbol": "NIFTY",
            "start_date": "2024-03-01",
            "end_date": "2024-01-01",
            "capital": 100000,
        })
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_create_backtest_invalid_capital():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/backtest", json={
            "symbol": "NIFTY",
            "start_date": "2024-01-01",
            "end_date": "2024-03-01",
            "capital": -1000,
        })
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_post_returns_complete_result_synchronously():
    """POST run → result returned directly in the response (synchronous execution)."""
    mock_df = _mock_df()

    async def _fake_load_ohlcv(*args, **kwargs):
        return mock_df

    with patch("data.ohlcv_loader.load_ohlcv", new=_fake_load_ohlcv):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/backtest", json={
                "symbol": "NIFTY",
                "start_date": "2024-01-01",
                "end_date": "2024-03-01",
                "capital": 100000,
            })

    assert res.status_code == 200
    data = res.json()

    # Shape contract
    assert data["status"] == "COMPLETE"
    assert "id" in data
    assert "result" in data
    result = data["result"]
    assert "trades" in result
    assert "metrics" in result
    assert "equity_curve" in result
    assert "benchmark" in result

    # Metrics shape
    for key in ("total_trades", "win_rate", "net_pnl", "max_drawdown", "sharpe_ratio"):
        assert key in result["metrics"]


@pytest.mark.asyncio
async def test_post_returns_empty_result_when_no_data():
    """POST with no DB data → returns COMPLETE with 0 trades (not a 500 error)."""
    async def _empty_load(*args, **kwargs):
        return pd.DataFrame(columns=["o", "h", "l", "c", "v"])

    with patch("data.ohlcv_loader.load_ohlcv", new=_empty_load):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/backtest", json={
                "symbol": "NIFTY",
                "start_date": "2024-01-01",
                "end_date": "2024-03-01",
                "capital": 100000,
            })

    assert res.status_code == 200
    assert res.json()["result"]["metrics"]["total_trades"] == 0
