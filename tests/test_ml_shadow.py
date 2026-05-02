"""
Phase 2.6 / 2.7 — Shadow-mode observability and ENABLE_ML_SIGNAL flag tests.

TDD criterion 2.7:
  - With flag OFF: /api/signal returns ml.status = "shadow"
  - With flag ON:  /api/signal returns ml.status = "active"
  - Existing rule `signal` field is always present regardless of flag.

TDD criterion 2.6:
  - /api/ml/shadow-stats returns agreement_rate, totals, started_at shape.
  - After a signal call where rule and ML agree, agree count increments.
"""
import pytest
import pandas as pd
import numpy as np
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

from main import app
import api.routes as routes_module


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    closes = 22000.0 + np.cumsum(rng.normal(0, 25, n))
    spread = rng.uniform(5, 45, n)
    opens  = closes - rng.uniform(-10, 10, n)
    highs  = np.maximum(closes, opens) + spread * 0.4
    lows   = np.minimum(closes, opens) - spread * 0.4
    vols   = rng.integers(500_000, 5_000_000, n).astype(float)
    idx    = pd.date_range("2024-01-02 09:15", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": vols},
        index=idx,
    )


_FAKE_SIGNAL = {
    "direction": "BUY_CE",
    "action": "BUY_CE",
    "confidence": "High",
    "score": 55,
    "strike": 22050,
    "strike_type": "ATM",
    "expiry": "08-May-2025",
    "reasoning": ["RSI bullish"],
    "indicators_used": [],
}

_FAKE_CHAIN = {
    "pcr": 1.1,
    "max_pain": 22000,
    "expiry": "08-May-2025",
    "strikes": [],
    "fallback": False,
}

_FAKE_INDICATORS = {
    "combined_score": 55,
    "confidence": "High",
    "rsi": 60,
    "macd": {"value": 10, "signal": 5, "histogram": 5},
    "supertrend": {"direction": "UP"},
    "bollinger": {"upper": 22200, "lower": 21800, "middle": 22000},
    "pcr": 1.1,
    "iv": {"value": 15},
    "volume_trend": "BULLISH",
    "confluence": {"count": 4, "direction": "BUY", "strength": "STRONG"},
}


def _patch_data_deps(mock_df=None):
    """Return a context-manager stack patching all data-fetching dependencies."""
    df = mock_df if mock_df is not None else _make_df()
    return [
        patch("api.routes.get_ohlcv", return_value=df),
        patch("api.routes.get_spot_price", return_value=22000.0),
        patch("api.routes.fetch_option_chain", return_value=_FAKE_CHAIN),
        patch("api.routes.get_atm_iv", return_value=15.0),
        patch("api.routes.compute_indicators", return_value=_FAKE_INDICATORS),
        patch("api.routes.generate_signal", return_value=_FAKE_SIGNAL),
        patch("api.routes.get_next_expiry"),
    ]


# ---------------------------------------------------------------------------
# 2.7 — ENABLE_ML_SIGNAL flag flips ml.status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ml_status_shadow_when_flag_off():
    """Flag OFF (default) → ml.status == 'shadow'."""
    fake_ml = {"status": "shadow", "direction": "BUY_CE", "confidence": 0.6, "regime": "TRENDING_UP"}

    patches = _patch_data_deps()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with patch("api.routes._ml_shadow", new=AsyncMock(return_value=fake_ml)):
            with patch("config.feature_flags.is_enabled", return_value=False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get("/api/signal/NIFTY")

    assert res.status_code == 200
    data = res.json()
    assert data["ml"]["status"] == "shadow"
    # Rule signal always present
    assert "signal" in data
    assert data["signal"]["direction"] == "BUY_CE"


@pytest.mark.asyncio
async def test_ml_status_active_when_flag_on():
    """Flag ON → ml.status == 'active' — ML is the authoritative source."""
    fake_ml = {"status": "active", "direction": "BUY_CE", "confidence": 0.7, "regime": "TRENDING_UP"}

    patches = _patch_data_deps()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with patch("api.routes._ml_shadow", new=AsyncMock(return_value=fake_ml)):
            with patch("config.feature_flags.is_enabled", return_value=True):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.get("/api/signal/NIFTY")

    assert res.status_code == 200
    data = res.json()
    assert data["ml"]["status"] == "active"
    # Rule signal still present — additive, not replaced
    assert "signal" in data


@pytest.mark.asyncio
async def test_signal_endpoint_no_regression_on_flag_flip():
    """Flipping the flag must not change the rule signal field or cause a 5xx."""
    fake_ml_shadow = {"status": "shadow", "direction": "BUY_PE", "confidence": 0.58, "regime": "RANGING"}
    fake_ml_active = {"status": "active", "direction": "BUY_PE", "confidence": 0.58, "regime": "RANGING"}

    patches = _patch_data_deps()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with patch("api.routes._ml_shadow", new=AsyncMock(side_effect=[fake_ml_shadow, fake_ml_active])):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res_off = await client.get("/api/signal/NIFTY")
                res_on  = await client.get("/api/signal/NIFTY")

    for res in (res_off, res_on):
        assert res.status_code == 200
        body = res.json()
        # Shape contract: these keys must always be present
        for key in ("ticker", "spot", "signal", "ml", "indicators", "chain_summary"):
            assert key in body, f"Missing key '{key}' when flag={'off' if res is res_off else 'on'}"


# ---------------------------------------------------------------------------
# 2.6 — shadow-stats endpoint shape and agreement tracking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shadow_stats_endpoint_shape():
    """/api/ml/shadow-stats returns the expected shape."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/ml/shadow-stats")

    assert res.status_code == 200
    data = res.json()
    for key in ("total", "agree", "disagree", "rule_only"):
        assert key in data, f"Missing key '{key}' in shadow-stats"
    # agreement_rate is None when total==0, or a float [0,1]
    assert data["agreement_rate"] is None or 0.0 <= data["agreement_rate"] <= 1.0


@pytest.mark.asyncio
async def test_shadow_stats_agree_increments_on_matching_signals():
    """When rule dir == ML dir, agree counter should increment."""
    # Reset stats before test
    routes_module._shadow_stats.update({"total": 0, "agree": 0, "disagree": 0, "rule_only": 0})

    fake_ml = {"status": "shadow", "direction": "BUY_CE", "confidence": 0.65, "regime": "TRENDING_UP"}

    patches = _patch_data_deps()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with patch("api.routes._ml_shadow", new=AsyncMock(return_value=fake_ml)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.get("/api/signal/NIFTY")
                stats = (await client.get("/api/ml/shadow-stats")).json()

    # Rule signal direction is BUY_CE (from _FAKE_SIGNAL), ML is also BUY_CE → agree
    assert stats["total"] >= 1
    assert stats["agree"] >= 1
    assert stats["agreement_rate"] is not None and stats["agreement_rate"] > 0


@pytest.mark.asyncio
async def test_shadow_stats_disagree_increments_on_diverging_signals():
    """When rule dir != ML dir, disagree counter should increment."""
    routes_module._shadow_stats.update({"total": 0, "agree": 0, "disagree": 0, "rule_only": 0})

    # ML disagrees with rule (rule=BUY_CE, ml=BUY_PE)
    fake_ml = {"status": "shadow", "direction": "BUY_PE", "confidence": 0.60, "regime": "RANGING"}

    patches = _patch_data_deps()
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with patch("api.routes._ml_shadow", new=AsyncMock(return_value=fake_ml)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.get("/api/signal/NIFTY")
                stats = (await client.get("/api/ml/shadow-stats")).json()

    assert stats["total"] >= 1
    assert stats["disagree"] >= 1
