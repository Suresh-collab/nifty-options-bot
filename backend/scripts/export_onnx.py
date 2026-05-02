#!/usr/bin/env python
"""
Convert trained sklearn models in model_registry → ONNX format in model_registry_onnx.

Run from the project root after Phase 2 training:
    pip install skl2onnx onnxmltools onnx          # already in backend/requirements.txt
    python backend/scripts/export_onnx.py

Requires DATABASE_URL in backend/.env or environment.

What gets exported
──────────────────
direction_model   → StandardScaler + XGBClassifier Pipeline (ONNX float[None,19])
                    Note: CalibratedClassifierCV wrapper is stripped; raw XGB probs used.
                    The directional signal (BUY_CE/BUY_PE/AVOID) is not affected.

regime_classifier → StandardScaler + KMeans Pipeline (ONNX float[None,3])
                    label_map stored as JSON in input_features column for post-processing.
"""
import asyncio
import io
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import joblib
import numpy as np
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

SYMBOLS   = ["NIFTY", "BANKNIFTY"]
INTERVAL  = "5m"
VERSION   = "v1-onnx"


# ── DB helpers ─────────────────────────────────────────────────────────────

async def _load_sklearn_artifact(session_factory, name: str, symbol: str, interval: str):
    async with session_factory() as session:
        row = await session.execute(
            text(
                "SELECT artifact FROM model_registry "
                "WHERE name=:name AND symbol=:symbol AND interval=:interval AND is_active=true "
                "ORDER BY trained_at DESC LIMIT 1"
            ),
            {"name": name, "symbol": symbol, "interval": interval},
        )
        result = row.fetchone()
    if result is None:
        return None
    return joblib.load(io.BytesIO(bytes(result[0])))


async def _save_onnx_artifact(session_factory, name: str, symbol: str, interval: str,
                               version: str, onnx_bytes: bytes, meta: dict) -> None:
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO model_registry_onnx "
                "  (name, symbol, interval, version, onnx_bytes, input_features) "
                "VALUES (:name, :symbol, :interval, :version, :onnx_bytes, :meta) "
                "ON CONFLICT (name, symbol, interval, version) DO UPDATE SET "
                "  onnx_bytes     = EXCLUDED.onnx_bytes, "
                "  input_features = EXCLUDED.input_features, "
                "  created_at     = now()"
            ),
            {
                "name":       name,
                "symbol":     symbol,
                "interval":   interval,
                "version":    version,
                "onnx_bytes": onnx_bytes,
                "meta":       json.dumps(meta),
            },
        )
        await session.commit()
    log.info("Saved ONNX  %s / %s / %s  (%d KB)", name, symbol, interval, len(onnx_bytes) // 1024)


# ── ONNX conversion ─────────────────────────────────────────────────────────

def _convert_direction_model(pipeline) -> bytes:
    """
    Convert direction Pipeline to ONNX.

    CalibratedClassifierCV is stripped — we extract a single base XGBClassifier
    from the first calibration fold and rebuild a simple StandardScaler→XGB pipeline.
    Raw XGB probabilities are used at inference; BUY_CE/BUY_PE/AVOID thresholds still apply.
    """
    from skl2onnx import convert_sklearn, update_registered_converter
    from skl2onnx.common.data_types import FloatTensorType
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBClassifier

    # Register XGBoost converter
    try:
        from onnxmltools.convert.xgboost.operator_converters.XGBoost import convert_xgboost
        from skl2onnx.common.shape_calculator import calculate_linear_classifier_output_shapes
        update_registered_converter(
            XGBClassifier,
            "XGBoostXGBClassifier",
            calculate_linear_classifier_output_shapes,
            convert_xgboost,
            options={"nocl": [True, False], "zipmap": [True, False, "columns"]},
        )
        log.info("Registered XGBoost→ONNX converter via onnxmltools")
    except Exception as e:
        log.warning("onnxmltools registration failed (%s) — trying skl2onnx native", e)

    # Extract base XGB from CalibratedClassifierCV
    calibrated = pipeline.named_steps["clf"]
    base_xgb = calibrated.calibrated_classifiers_[0].estimator  # XGBClassifier

    simple = Pipeline([
        ("scaler", pipeline.named_steps["scaler"]),
        ("clf",    base_xgb),
    ])

    from ml.model import FEATURE_COLS
    n_features = len(FEATURE_COLS)

    onnx_model = convert_sklearn(
        simple,
        initial_types=[("float_input", FloatTensorType([None, n_features]))],
        options={XGBClassifier: {"zipmap": False}},
        target_opset={"": 17, "ai.onnx.ml": 3},
    )
    return onnx_model.SerializeToString()


def _convert_regime_classifier(regime_clf) -> tuple[bytes, dict]:
    """
    Convert RegimeClassifier to ONNX.
    Returns (onnx_bytes, meta_dict) where meta contains label_map for post-processing.
    """
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    from sklearn.pipeline import Pipeline

    pipeline = Pipeline([
        ("scaler", regime_clf.scaler),
        ("kmeans", regime_clf.kmeans),
    ])

    onnx_model = convert_sklearn(
        pipeline,
        initial_types=[("float_input", FloatTensorType([None, 3]))],
    )
    onnx_bytes = onnx_model.SerializeToString()

    meta = {
        "feature_cols":  ["volatility", "momentum", "atr_pct"],
        "label_map":     {str(k): int(v) for k, v in regime_clf._label_map.items()},
        "regime_labels": {"0": "TRENDING_UP", "1": "TRENDING_DOWN", "2": "RANGING"},
    }
    return onnx_bytes, meta


# ── Main ────────────────────────────────────────────────────────────────────

async def main():
    from db.base import get_session_factory
    factory = get_session_factory()

    total_ok = 0
    for symbol in SYMBOLS:
        log.info("═══ %s ═══", symbol)

        # direction_model
        log.info("Loading direction_model …")
        direction_model = await _load_sklearn_artifact(factory, "direction_model", symbol, INTERVAL)
        if direction_model is None:
            log.warning("No trained direction_model for %s — run train.py first", symbol)
        else:
            log.info("Converting to ONNX …")
            try:
                onnx_bytes = _convert_direction_model(direction_model)
                from ml.model import FEATURE_COLS
                await _save_onnx_artifact(factory, "direction_model", symbol, INTERVAL, VERSION,
                                          onnx_bytes, {"feature_cols": FEATURE_COLS})
                total_ok += 1
            except Exception as e:
                log.error("direction_model conversion FAILED for %s: %s", symbol, e)

        # regime_classifier
        log.info("Loading regime_classifier …")
        regime_clf = await _load_sklearn_artifact(factory, "regime_classifier", symbol, INTERVAL)
        if regime_clf is None:
            log.warning("No trained regime_classifier for %s — run train.py first", symbol)
        else:
            log.info("Converting to ONNX …")
            try:
                onnx_bytes, meta = _convert_regime_classifier(regime_clf)
                await _save_onnx_artifact(factory, "regime_classifier", symbol, INTERVAL, VERSION,
                                          onnx_bytes, meta)
                total_ok += 1
            except Exception as e:
                log.error("regime_classifier conversion FAILED for %s: %s", symbol, e)

    log.info("Done — %d/%d models exported successfully", total_ok, len(SYMBOLS) * 2)
    if total_ok == len(SYMBOLS) * 2:
        log.info("Next step: redeploy Vercel — ML shadow panel will be live in production.")
    else:
        log.warning("Some models failed. Check errors above and re-run after fixing.")


if __name__ == "__main__":
    asyncio.run(main())
