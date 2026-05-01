#!/usr/bin/env python
"""
Phase 2 — Local model training script.

Run from the project root:
    python backend/scripts/train.py [--symbol NIFTY|BANKNIFTY|ALL] [--version v1]

What it does
────────────
1. Loads OHLCV data from Neon (ohlcv_cache table, 5m interval)
2. Builds the feature matrix (ml.features)
3. Fits the regime classifier (ml.regime) and injects regime labels as a feature
4. Trains the XGBoost direction model (ml.model)
5. Prints evaluation metrics (AUC, Brier score)
6. Saves both models to Neon model_registry and marks them active

Prerequisites
─────────────
- Run `python backend/scripts/load_data.py` (or use Load Market Data button on UI)
  first so that ohlcv_cache is populated.
- .env must contain DATABASE_URL.
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# Allow running from project root OR from backend/
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND    = os.path.join(_SCRIPT_DIR, "..")
_ROOT       = os.path.join(_BACKEND, "..")
for _p in (_ROOT, _BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, ".env"))

from db.base import get_session_factory
from data.ohlcv_loader import load_ohlcv
from ml.features import build_features, build_target
from ml.regime import RegimeClassifier
from ml.model import train
from ml.registry import save_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SYMBOLS = ["NIFTY", "BANKNIFTY"]


async def train_symbol(symbol: str, version: str) -> None:
    logger.info("═══ Training models for %s ═══", symbol)

    # ── 1. Load OHLCV from DB ─────────────────────────────────────────
    factory = get_session_factory()
    async with factory() as session:
        end   = datetime.now(timezone.utc)
        start = end.replace(year=end.year - 1)   # 1 year of 5m data
        df = await load_ohlcv(symbol, "5m", start, end, session)

    if df.empty or len(df) < 200:
        logger.error("Not enough data for %s (%d rows). Run 'Load Market Data' first.", symbol, len(df))
        return

    logger.info("Loaded %d bars for %s (5m)", len(df), symbol)
    train_start = df.index[0].date().isoformat()
    train_end   = df.index[-1].date().isoformat()

    # ── 2. Regime classifier ──────────────────────────────────────────
    regime_clf = RegimeClassifier()
    regime_clf.fit(df)
    logger.info("Regime classifier fitted")

    # ── 3. Feature matrix + target ────────────────────────────────────
    feat   = build_features(df)
    target = build_target(df, horizon=3)

    # Inject regime label as a feature
    feat["regime"] = regime_clf.predict(df).reindex(feat.index).fillna(2)

    logger.info("Feature matrix: %d rows × %d cols", *feat.shape)

    # ── 4. Train direction model ──────────────────────────────────────
    result = train(feat, target)
    logger.info(
        "Direction model AUC=%.4f  Brier=%.4f  (train=%d, test=%d)",
        result.auc, result.brier, result.n_train, result.n_test,
    )

    if result.auc < 0.52:
        logger.warning("⚠ AUC %.4f is low — model may not be useful. "
                       "Consider loading more data and re-training.", result.auc)

    # Top 5 features
    top5 = sorted(result.feature_importance.items(), key=lambda x: x[1], reverse=True)[:5]
    logger.info("Top features: %s", ", ".join(f"{k}={v:.3f}" for k, v in top5))

    # ── 5. Save to Neon ───────────────────────────────────────────────
    metrics = {
        "auc":     round(result.auc, 4),
        "brier":   round(result.brier, 4),
        "n_train": result.n_train,
        "n_test":  result.n_test,
    }

    await save_model(
        name="regime_classifier",
        version=version,
        symbol=symbol,
        interval="5m",
        model_obj=regime_clf,
        train_start=train_start,
        train_end=train_end,
        metrics={},
        set_active=True,
    )
    logger.info("Saved regime_classifier v%s for %s", version, symbol)

    await save_model(
        name="direction_model",
        version=version,
        symbol=symbol,
        interval="5m",
        model_obj=result.pipeline,
        train_start=train_start,
        train_end=train_end,
        metrics=metrics,
        set_active=True,
    )
    logger.info("Saved direction_model v%s for %s  AUC=%.4f", version, symbol, result.auc)


async def main(symbols: list[str], version: str) -> None:
    for sym in symbols:
        await train_symbol(sym, version)
    logger.info("Training complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Phase 2 ML models")
    parser.add_argument("--symbol", default="ALL",
                        help="NIFTY | BANKNIFTY | ALL  (default: ALL)")
    parser.add_argument("--version", default="v1",
                        help="Model version string stored in Neon (default: v1)")
    args = parser.parse_args()

    syms = SYMBOLS if args.symbol.upper() == "ALL" else [args.symbol.upper()]
    asyncio.run(main(syms, args.version))
