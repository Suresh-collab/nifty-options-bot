"""
Tests for the leading-indicator integration:
  - new feature flags default to False (existing behavior unchanged)
  - ml.features.build_features() emits the same columns when the flag is OFF
  - build_features() adds rsi_divergence when the flag is ON
  - api.ws._oi_snapshot_poller() no-ops when ENABLE_OI_FLOW_LOGGING is OFF
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest


# ── helper: a synthetic OHLCV frame with enough rows for indicators ───────
def _sample_df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base = np.linspace(100, 120, n)
    noise = rng.normal(0, 0.5, n)
    close = base + noise
    high = close + np.abs(rng.normal(0.5, 0.2, n))
    low = close - np.abs(rng.normal(0.5, 0.2, n))
    open_ = close + rng.normal(0, 0.3, n)
    vol = rng.integers(1_000, 5_000, n).astype(float)
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"o": open_, "h": high, "l": low, "c": close, "v": vol},
                        index=idx)


# ── TC-1: flags default OFF ───────────────────────────────────────────────
def test_tc1_new_flags_default_off():
    from config import feature_flags
    feature_flags._overrides.clear()
    assert feature_flags.is_enabled("ENABLE_DIVERGENCE_SIGNAL") is False
    assert feature_flags.is_enabled("ENABLE_DIVERGENCE_FEATURE") is False
    assert feature_flags.is_enabled("ENABLE_OI_FLOW_LOGGING") is False


# ── TC-2: build_features unchanged when flag OFF ──────────────────────────
def test_tc2_build_features_unchanged_when_off():
    from config import feature_flags
    feature_flags._overrides.clear()
    feature_flags.set_flag("ENABLE_DIVERGENCE_FEATURE", False)

    from ml.features import build_features
    df = _sample_df()
    feat = build_features(df)
    assert "rsi_divergence" not in feat.columns
    # Sanity: the original feature set is intact
    for col in ("rsi", "macd_line", "supertrend_dir", "bb_pos", "atr_pct"):
        assert col in feat.columns


# ── TC-3: rsi_divergence appears when flag ON ─────────────────────────────
def test_tc3_build_features_adds_divergence_when_on():
    from config import feature_flags
    feature_flags._overrides.clear()
    feature_flags.set_flag("ENABLE_DIVERGENCE_FEATURE", True)

    from ml.features import build_features
    df = _sample_df()
    feat = build_features(df)
    feature_flags.set_flag("ENABLE_DIVERGENCE_FEATURE", False)   # restore

    assert "rsi_divergence" in feat.columns
    # Should be in {-1, 0, +1}
    uniq = set(np.unique(feat["rsi_divergence"].values).tolist())
    assert uniq.issubset({-1.0, 0.0, 1.0})


# ── TC-4: OI poller skips when flag OFF ──────────────────────────────────
def test_tc4_oi_poller_skips_when_flag_off():
    """
    With the flag OFF the poller must reach asyncio.sleep, hit the flag check,
    and continue without calling fetch_option_chain or log_oi_snapshot.
    """
    from api import ws
    from config import feature_flags
    feature_flags._overrides.clear()
    feature_flags.set_flag("ENABLE_OI_FLOW_LOGGING", False)

    async def runner():
        with patch("data.options_chain.fetch_option_chain") as fc, \
             patch("data.market_data.get_spot_price", return_value=23500.0), \
             patch("data.market_data.is_market_open", return_value=True), \
             patch("data.oi_snapshot_logger.log_oi_snapshot") as log_fn:
            task = asyncio.create_task(ws._oi_snapshot_poller(
                interval=0.01, tickers=("NIFTY",),
            ))
            # let it loop a couple of times then cancel
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            # Neither path should have been called while the flag is off
            fc.assert_not_called()
            log_fn.assert_not_called()

    asyncio.run(runner())


# ── TC-5: OI poller skips when market closed (flag ON) ────────────────────
def test_tc5_oi_poller_skips_when_market_closed():
    from api import ws
    from config import feature_flags
    feature_flags._overrides.clear()
    feature_flags.set_flag("ENABLE_OI_FLOW_LOGGING", True)

    async def runner():
        with patch("data.options_chain.fetch_option_chain") as fc, \
             patch("data.market_data.get_spot_price", return_value=23500.0), \
             patch("data.market_data.is_market_open", return_value=False), \
             patch("data.oi_snapshot_logger.log_oi_snapshot") as log_fn:
            task = asyncio.create_task(ws._oi_snapshot_poller(
                interval=0.01, tickers=("NIFTY",),
            ))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            fc.assert_not_called()
            log_fn.assert_not_called()

    asyncio.run(runner())
    feature_flags.set_flag("ENABLE_OI_FLOW_LOGGING", False)   # restore


# ── TC-6: OI poller calls logger when flag ON and market open ─────────────
def test_tc6_oi_poller_calls_logger_when_active():
    from api import ws
    from config import feature_flags
    feature_flags._overrides.clear()
    feature_flags.set_flag("ENABLE_OI_FLOW_LOGGING", True)

    fake_chain = {"ticker": "NIFTY", "spot": 23500, "strikes": [], "fallback": False,
                  "total_ce_oi": 100, "total_pe_oi": 100, "pcr": 1.0, "expiry": "16-May"}

    async def fake_log(_chain):   # async stub for log_oi_snapshot
        return "snap-123"

    async def runner():
        with patch("data.options_chain.fetch_option_chain", return_value=fake_chain) as fc, \
             patch("data.market_data.get_spot_price", return_value=23500.0), \
             patch("data.market_data.is_market_open", return_value=True), \
             patch("data.oi_snapshot_logger.log_oi_snapshot", side_effect=fake_log) as log_fn:
            task = asyncio.create_task(ws._oi_snapshot_poller(
                interval=0.02, tickers=("NIFTY",),
            ))
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            assert fc.called
            assert log_fn.called

    asyncio.run(runner())
    feature_flags.set_flag("ENABLE_OI_FLOW_LOGGING", False)   # restore


# ── TC-7: in-memory override resets via clear/set ─────────────────────────
def test_tc7_set_flag_persists_within_session():
    from config import feature_flags
    feature_flags._overrides.clear()
    assert feature_flags.is_enabled("ENABLE_DIVERGENCE_FEATURE") is False
    feature_flags.set_flag("ENABLE_DIVERGENCE_FEATURE", True)
    assert feature_flags.is_enabled("ENABLE_DIVERGENCE_FEATURE") is True
    feature_flags._overrides.clear()
    assert feature_flags.is_enabled("ENABLE_DIVERGENCE_FEATURE") is False
