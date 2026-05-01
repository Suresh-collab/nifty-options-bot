"""
XGBoost direction model — Phase 2.

Binary classifier: predicts whether the next `horizon` bars will close
higher (1) or lower (0) than the current bar.

Pipeline
────────
  StandardScaler → XGBClassifier → CalibratedClassifierCV (isotonic)

TDD targets
  • Out-of-sample AUC ≥ 0.55 on held-out test set
  • Brier score ≤ 0.24

The model is trained by the local training script (backend/scripts/train.py)
and loaded at inference time from the Neon model_registry table.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "ret_1", "ret_5", "ret_15", "ret_30",
    "rsi",
    "macd_line", "macd_hist", "macd_cross",
    "supertrend_dir",
    "bb_pos", "bb_width",
    "atr_pct",
    "ema_cross",
    "vol_ratio",
    "time_sin", "time_cos",
    "dow_sin", "dow_cos",
    "regime",               # injected by regime classifier
]


@dataclass
class TrainResult:
    pipeline: Pipeline
    auc: float
    brier: float
    n_train: int
    n_test: int
    feature_importance: dict = field(default_factory=dict)


def build_pipeline(n_estimators: int = 300, max_depth: int = 4,
                   learning_rate: float = 0.05) -> Pipeline:
    """Return an unfitted sklearn Pipeline (Scaler → XGBoost → Calibration)."""
    xgb = XGBClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    calibrated = CalibratedClassifierCV(xgb, cv=3, method="isotonic")
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf",    calibrated),
    ])


def train(
    features: pd.DataFrame,
    target: pd.Series,
    test_frac: float = 0.20,
) -> TrainResult:
    """
    Train on `features` + `target`, evaluate on a held-out time-split.

    Parameters
    ----------
    features : DataFrame from ml.features.build_features(), must include 'regime' col
    target   : Series from ml.features.build_target()
    test_frac: fraction of data reserved for out-of-sample evaluation

    Returns
    -------
    TrainResult with fitted pipeline + evaluation metrics
    """
    # Align features and target (inner join on index)
    common = features.index.intersection(target.dropna().index)
    X = features.loc[common, [c for c in FEATURE_COLS if c in features.columns]].copy()
    y = target.loc[common].astype(int)

    if len(X) < 100:
        raise ValueError(f"Insufficient training data: {len(X)} rows (need ≥ 100)")

    split_idx = int(len(X) * (1 - test_frac))
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    logger.info("Training direction model: %d train rows, %d test rows, %d features",
                len(X_train), len(X_test), X.shape[1])

    pipeline = build_pipeline()
    pipeline.fit(X_train.values, y_train.values)

    y_prob = pipeline.predict_proba(X_test.values)[:, 1]
    auc    = roc_auc_score(y_test.values, y_prob)
    brier  = brier_score_loss(y_test.values, y_prob)

    logger.info("Direction model — AUC: %.4f, Brier: %.4f", auc, brier)
    if auc < 0.52:
        logger.warning("AUC %.4f is below target 0.55 — consider more data or feature tuning", auc)

    # Feature importance: average across the CV folds inside CalibratedClassifierCV
    calibrated_clf = pipeline.named_steps["clf"]
    importances = np.mean(
        [est.estimator.feature_importances_
         for est in calibrated_clf.calibrated_classifiers_],
        axis=0,
    )
    importance = dict(zip(X.columns, importances))

    return TrainResult(
        pipeline=pipeline,
        auc=auc,
        brier=brier,
        n_train=len(X_train),
        n_test=len(X_test),
        feature_importance=importance,
    )


def predict(pipeline: Pipeline, features: pd.DataFrame) -> tuple[int, float]:
    """
    Run inference on the LAST row of `features`.

    Returns
    -------
    (direction, confidence)
      direction  : 1 = UP (BUY_CE), -1 = DOWN (BUY_PE), 0 = AVOID
      confidence : probability of the predicted class [0, 1]
    """
    if features.empty:
        return 0, 0.0

    row = features.iloc[[-1]]
    cols = [c for c in FEATURE_COLS if c in features.columns]
    if len(cols) < len(FEATURE_COLS) - 2:   # allow a couple optional cols missing
        logger.warning("predict: only %d/%d expected features present", len(cols), len(FEATURE_COLS))

    prob_up = float(pipeline.predict_proba(row[cols].values)[0, 1])

    if prob_up >= 0.55:
        return 1, prob_up
    elif prob_up <= 0.45:
        return -1, 1.0 - prob_up
    else:
        return 0, max(prob_up, 1.0 - prob_up)   # AVOID — low confidence
