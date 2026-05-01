"""
Market regime classifier — Phase 2.

Uses KMeans(n_clusters=3) on three rolling features:
  - 20-bar rolling volatility of returns
  - 5-bar cumulative return direction
  - ATR as % of price (volatility level)

Regimes are re-labelled after fitting based on centroid characteristics:
  0 → TRENDING_UP    (positive return, moderate volatility)
  1 → TRENDING_DOWN  (negative return, moderate volatility)
  2 → RANGING        (near-zero return, low volatility)

The labels are stable labels — the actual KMeans cluster IDs are mapped
to these names after fitting so results are interpretable.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

REGIME_LABELS = {0: "TRENDING_UP", 1: "TRENDING_DOWN", 2: "RANGING"}
N_CLUSTERS = 3


class RegimeClassifier:
    """Fits a KMeans regime model and attaches regime labels to OHLCV data."""

    def __init__(self, n_clusters: int = N_CLUSTERS, random_state: int = 42):
        self.n_clusters    = n_clusters
        self.random_state  = random_state
        self.kmeans: Optional[KMeans]          = None
        self.scaler: Optional[StandardScaler]  = None
        self._label_map: dict[int, int] = {}   # raw cluster id → stable label id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, df: pd.DataFrame) -> "RegimeClassifier":
        """Fit on OHLCV DataFrame. Returns self."""
        X = self._build_regime_features(df)
        if X.empty or len(X) < self.n_clusters * 10:
            raise ValueError(f"Not enough data to fit regime classifier (got {len(X)} rows)")

        self.scaler = StandardScaler()
        Xs = self.scaler.fit_transform(X.values)

        self.kmeans = KMeans(
            n_clusters=self.n_clusters,
            random_state=self.random_state,
            n_init=10,
        )
        raw_labels = self.kmeans.fit_predict(Xs)

        # Build label map: assign stable IDs based on centroid characteristics
        self._label_map = _build_label_map(self.kmeans.cluster_centers_, self.scaler)
        logger.info("Regime classifier fitted on %d bars. Cluster sizes: %s",
                    len(X), np.bincount(raw_labels).tolist())
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        """
        Return a Series of integer regime labels (0/1/2) aligned to df's index.
        Rows where regime features are NaN get label -1 (unknown).
        """
        if self.kmeans is None or self.scaler is None:
            raise RuntimeError("RegimeClassifier must be fitted before predict()")

        X = self._build_regime_features(df)
        result = pd.Series(-1, index=df.index, dtype=int, name="regime")

        if X.empty:
            return result

        Xs = self.scaler.transform(X.values)
        raw = self.kmeans.predict(Xs)
        stable = np.array([self._label_map.get(r, 2) for r in raw], dtype=int)
        result.loc[X.index] = stable
        return result

    def predict_label(self, df: pd.DataFrame) -> pd.Series:
        """Return string labels ('TRENDING_UP', etc.) aligned to df's index."""
        nums = self.predict(df)
        return nums.map(lambda x: REGIME_LABELS.get(x, "UNKNOWN"))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _build_regime_features(df: pd.DataFrame) -> pd.DataFrame:
        c = df["c"]
        ret = c.pct_change()

        feat = pd.DataFrame(index=df.index)
        feat["volatility"] = ret.rolling(20).std()        # rolling vol
        feat["momentum"]   = c.pct_change(5)              # 5-bar return
        feat["atr_pct"]    = _rolling_atr(df) / c.replace(0, np.nan)

        return feat.dropna()


def _rolling_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["h"], df["l"], df["c"]
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _build_label_map(centers: np.ndarray, scaler: StandardScaler) -> dict[int, int]:
    """
    Map raw KMeans cluster IDs to stable regime IDs:
      most-positive momentum centroid  → 0 (TRENDING_UP)
      most-negative momentum centroid  → 1 (TRENDING_DOWN)
      remaining                        → 2 (RANGING)

    `centers` is in the scaled space; we recover original-scale momentum
    using the scaler's mean/std for the momentum feature (index 1).
    """
    # momentum is feature index 1 in _build_regime_features
    momentum_scaled = centers[:, 1]
    sorted_ids = np.argsort(momentum_scaled)  # ascending

    label_map: dict[int, int] = {}
    label_map[int(sorted_ids[-1])] = 0   # highest momentum → TRENDING_UP
    label_map[int(sorted_ids[0])]  = 1   # lowest momentum  → TRENDING_DOWN
    # middle cluster → RANGING
    for i in range(len(sorted_ids)):
        if int(sorted_ids[i]) not in label_map:
            label_map[int(sorted_ids[i])] = 2
    return label_map
