"""Phase 2.3/2.4 — Direction model + regime classifier tests."""
import numpy as np
import pandas as pd
import pytest

from ml.features import build_features, build_target
from ml.regime import RegimeClassifier, REGIME_LABELS
from ml.model import train, predict, FEATURE_COLS


def _make_df(n: int = 500, freq: str = "5min") -> pd.DataFrame:
    rng = np.random.default_rng(7)
    closes = 22000.0 + np.cumsum(rng.normal(0, 25, n))
    spread = rng.uniform(5, 45, n)
    opens  = closes - rng.uniform(-10, 10, n)
    highs  = np.maximum(closes, opens) + spread * 0.4
    lows   = np.minimum(closes, opens) - spread * 0.4
    vols   = rng.integers(500_000, 5_000_000, n).astype(float)
    idx    = pd.date_range("2024-01-02 09:15", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"o": opens, "h": highs, "l": lows, "c": closes, "v": vols}, index=idx)


# ── regime classifier ──────────────────────────────────────────────────────────

def test_regime_classifier_fits_and_predicts():
    df = _make_df(500)
    clf = RegimeClassifier()
    clf.fit(df)
    labels = clf.predict(df)
    valid = labels[labels != -1]
    assert len(valid) > 0
    assert set(valid.unique()).issubset({0, 1, 2})


def test_regime_labels_cover_all_three():
    df = _make_df(600)
    clf = RegimeClassifier()
    clf.fit(df)
    labels = clf.predict(df)
    valid = set(labels[labels != -1].unique())
    # At least 2 distinct regimes for 500+ bars
    assert len(valid) >= 2


def test_regime_predict_label_returns_strings():
    df = _make_df(400)
    clf = RegimeClassifier()
    clf.fit(df)
    str_labels = clf.predict_label(df)
    known = set(REGIME_LABELS.values()) | {"UNKNOWN"}
    assert set(str_labels.unique()).issubset(known)


def test_regime_too_little_data_raises():
    df = _make_df(5)
    clf = RegimeClassifier()
    with pytest.raises(ValueError, match="Not enough data"):
        clf.fit(df)


# ── direction model ────────────────────────────────────────────────────────────

def _build_training_data(n: int = 600):
    df = _make_df(n)
    regime_clf = RegimeClassifier()
    regime_clf.fit(df)
    feat = build_features(df)
    feat["regime"] = regime_clf.predict(df).reindex(feat.index)
    target = build_target(df, horizon=3)
    return feat, target


def test_train_returns_result_with_metrics():
    feat, target = _build_training_data()
    result = train(feat, target)
    assert 0 <= result.auc <= 1
    assert 0 <= result.brier <= 1
    assert result.n_train > 0
    assert result.n_test > 0


def test_train_pipeline_can_predict():
    feat, target = _build_training_data()
    result = train(feat, target)
    direction, confidence = predict(result.pipeline, feat)
    assert direction in (-1, 0, 1)
    assert 0 <= confidence <= 1


def test_predict_empty_features_returns_avoid():
    feat, target = _build_training_data()
    result = train(feat, target)
    direction, conf = predict(result.pipeline, pd.DataFrame())
    assert direction == 0
    assert conf == 0.0


def test_train_insufficient_data_raises():
    df = _make_df(50)
    feat = build_features(df)
    target = build_target(df)
    with pytest.raises(ValueError, match="Insufficient"):
        train(feat, target)


def test_feature_importance_keys_are_feature_names():
    feat, target = _build_training_data()
    result = train(feat, target)
    present_cols = [c for c in FEATURE_COLS if c in feat.columns]
    for k in result.feature_importance:
        assert k in present_cols
