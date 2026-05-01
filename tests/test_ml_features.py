"""Phase 2.1 — Feature pipeline tests."""
import numpy as np
import pandas as pd
import pytest

from ml.features import build_features, build_target, _is_intraday


def _make_df(n: int = 200, freq: str = "5min") -> pd.DataFrame:
    rng = np.random.default_rng(0)
    closes = 22000.0 + np.cumsum(rng.normal(0, 20, n))
    spread = rng.uniform(5, 40, n)
    opens  = closes - rng.uniform(-8, 8, n)
    highs  = np.maximum(closes, opens) + spread * 0.4
    lows   = np.minimum(closes, opens) - spread * 0.4
    vols   = rng.integers(500_000, 3_000_000, n).astype(float)
    idx    = pd.date_range("2024-01-02 09:15", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"o": opens, "h": highs, "l": lows, "c": closes, "v": vols}, index=idx)


# ── determinism ────────────────────────────────────────────────────────────────

def test_build_features_deterministic():
    df = _make_df()
    f1 = build_features(df)
    f2 = build_features(df)
    pd.testing.assert_frame_equal(f1, f2)


# ── no look-ahead leakage ──────────────────────────────────────────────────────

def test_no_lookahead_mutation():
    """Mutating a future candle must NOT change features at past rows."""
    df = _make_df(300)
    feat_before = build_features(df.copy())

    # Corrupt the last 5 bars
    df_mutated = df.copy()
    df_mutated.iloc[-5:, df_mutated.columns.get_loc("c")] *= 1.5
    feat_after = build_features(df_mutated)

    # Features for bars well before the mutation must be identical
    common_idx = feat_before.index.intersection(feat_after.index)
    safe_idx = common_idx[:-10]   # exclude the last 10 rows (rolling windows may reach back)
    pd.testing.assert_frame_equal(
        feat_before.loc[safe_idx], feat_after.loc[safe_idx]
    )


# ── shape and columns ──────────────────────────────────────────────────────────

def test_build_features_columns_present():
    df = _make_df()
    feat = build_features(df)
    expected = {
        "ret_1", "ret_5", "ret_15", "ret_30",
        "rsi", "macd_line", "macd_hist", "macd_cross",
        "supertrend_dir", "bb_pos", "bb_width",
        "atr_pct", "ema_cross", "vol_ratio",
        "time_sin", "time_cos", "dow_sin", "dow_cos",
    }
    assert expected.issubset(set(feat.columns))


def test_build_features_no_nan():
    df = _make_df()
    feat = build_features(df)
    assert feat.isna().sum().sum() == 0


def test_build_features_no_inf():
    df = _make_df()
    feat = build_features(df)
    assert np.isfinite(feat.values).all()


def test_build_features_too_short_returns_empty():
    df = _make_df(n=10)
    assert build_features(df).empty


# ── target ─────────────────────────────────────────────────────────────────────

def test_build_target_binary():
    df = _make_df()
    target = build_target(df, horizon=3)
    valid = target.dropna()
    assert set(valid.unique()).issubset({0.0, 1.0})


def test_build_target_last_rows_are_nan():
    df = _make_df(100)
    target = build_target(df, horizon=3)
    assert target.iloc[-3:].isna().all()


def test_build_target_not_nan_before_end():
    df = _make_df(100)
    target = build_target(df, horizon=3)
    assert target.iloc[:-3].notna().all()


# ── intraday detection ─────────────────────────────────────────────────────────

def test_is_intraday_5m():
    df = _make_df(freq="5min")
    assert _is_intraday(df) is True


def test_is_intraday_daily():
    df = _make_df(n=100, freq="1D")
    assert _is_intraday(df) is False
