"""1.4 — backtest API endpoint integration tests."""
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
import pandas as pd
import numpy as np
from datetime import timezone

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
async def test_create_backtest_returns_id():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/backtest", json={
            "symbol": "NIFTY",
            "start_date": "2024-01-01",
            "end_date": "2024-03-01",
            "capital": 100000,
        })
    assert res.status_code == 200
    body = res.json()
    assert "id" in body
    assert body["status"] == "PENDING"


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
async def test_get_backtest_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/backtest/nonexistent-uuid")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_post_poll_get_complete():
    """POST run → wait for background task → GET shows COMPLETE with result shape."""
    mock_df = _mock_df()

    async def _fake_load_ohlcv(*args, **kwargs):
        return mock_df

    with patch("data.ohlcv_loader.load_ohlcv", new=_fake_load_ohlcv):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            post_res = await client.post("/api/backtest", json={
                "symbol": "NIFTY",
                "start_date": "2024-01-01",
                "end_date": "2024-03-01",
                "capital": 100000,
            })
            assert post_res.status_code == 200
            run_id = post_res.json()["id"]

            # Allow background task to run
            await asyncio.sleep(0.5)

            get_res = await client.get(f"/api/backtest/{run_id}")

    assert get_res.status_code == 200
    data = get_res.json()
    assert data["status"] in ("RUNNING", "COMPLETE", "ERROR")
    if data["status"] == "COMPLETE":
        assert "trades" in data["result"]
        assert "metrics" in data["result"]
        assert "equity_curve" in data["result"]
        assert "benchmark" in data["result"]
        # Verify metrics shape
        metrics = data["result"]["metrics"]
        for key in ("total_trades", "win_rate", "net_pnl", "max_drawdown", "sharpe_ratio"):
            assert key in metrics
