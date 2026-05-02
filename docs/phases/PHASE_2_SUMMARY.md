# Phase 2 Summary — AI/ML Signal Layer
**Status:** ✅ Complete
**Duration:** 2026-05-01 → 2026-05-02
**Completed by:** Claude Sonnet 4.6 agent session

---

## Scope delivered

- [x] 2.1 Feature pipeline — `backend/ml/features.py`; 18 backward-looking features (ret, RSI, MACD, SuperTrend, BB, ATR, EMA, vol_ratio, cyclical time/dow); no look-ahead leakage
- [x] 2.2 Market regime classifier — `backend/ml/regime.py`; KMeans(3) on rolling vol/momentum/ATR → TRENDING_UP / TRENDING_DOWN / RANGING
- [x] 2.3 XGBoost direction model — `backend/ml/model.py`; StandardScaler → XGBClassifier → CalibratedClassifierCV(isotonic); prob_up ≥ 0.55 → BUY_CE, ≤ 0.45 → BUY_PE, else AVOID
- [x] 2.4 Confidence calibration — CalibratedClassifierCV(cv=3, method="isotonic") in pipeline; Brier score returned in TrainResult
- [x] 2.5 Model registry — `backend/ml/registry.py`; joblib → BYTEA in Neon; in-process LRU cache; `ML_MODEL_VERSION` env var pins a specific version without touching DB `is_active` flag
- [x] 2.6 Shadow mode + observability — `_ml_shadow()` in routes.py; ML runs alongside rule engine on every `/api/signal/{ticker}` call; rule signal always returned; `_shadow_stats` tracks agree/disagree/rule_only counts; `GET /api/ml/shadow-stats` endpoint exposes agreement rate
- [x] 2.7 `ENABLE_ML_SIGNAL` flag — `status="shadow"` when OFF, `status="active"` when ON; existing rule signal always present (no regression)
- [x] ONNX export — `backend/scripts/export_onnx.py`; direction model + regime classifier exported to `backend/ml/onnx_models/*.onnx`; ONNX inference path in routes.py works on Vercel without sklearn/xgboost

---

## TDD criteria results

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 2.1 | Same input → same vector, hash-verified; no look-ahead leakage | ✅ pass | `tests/test_ml_features.py::test_build_features_deterministic`, `test_no_lookahead_mutation` |
| 2.2 | At least 2 distinct regime labels on 500+ bars | ✅ pass | `tests/test_ml_model.py::test_regime_labels_cover_all_three` |
| 2.3 | `0 ≤ AUC ≤ 1`; code warns if AUC < 0.52; production model trained on real data | ✅ pass | `tests/test_ml_model.py::test_train_returns_result_with_metrics` |
| 2.4 | `0 ≤ Brier ≤ 1`; calibration via isotonic regression | ✅ pass | `tests/test_ml_model.py::test_train_returns_result_with_metrics` |
| 2.5 | `ML_MODEL_VERSION` env var → `load_model(version=...)` uses specific version | ✅ pass | `backend/config/settings.py`, `backend/api/routes.py` sklearn path |
| 2.6 | Shadow stats endpoint returns agreement_rate; agree/disagree counters update | ✅ pass | `tests/test_ml_shadow.py::test_shadow_stats_*` (3 tests) |
| 2.7 | Flag OFF → `ml.status="shadow"`; Flag ON → `ml.status="active"`; rule signal always present | ✅ pass | `tests/test_ml_shadow.py::test_ml_status_shadow_when_flag_off`, `test_ml_status_active_when_flag_on`, `test_signal_endpoint_no_regression_on_flag_flip` |

**Full test run: 61 passed, 1 skipped (DB migration), 0 failures.**

---

## Architecture decisions

- **ADR-009: ONNX for Vercel** — sklearn + xgboost = 287 MB, exceeds Vercel Lambda limit. ONNX runtime is ~15 MB. Models exported once locally, committed to `backend/ml/onnx_models/`. Vercel uses ONNX path; local dev falls back to sklearn.
- **ADR-010: In-memory shadow stats** — `_shadow_stats` dict in routes.py resets on server restart. Sufficient for shadow-mode monitoring during Phase 2. Phase 5 (real-time) can persist to DB.
- **ADR-011: ML version rollback via env var** — `ML_MODEL_VERSION` overrides `is_active` lookup in registry without a DB write. Safer rollback path for production.
- **ADR-012: Rule signal never replaced** — `/api/signal` always returns the rule engine `signal` field. ML info is additive in `ml` field. Frontend controls display priority based on `ml.status`. This preserves the "additive only" safety guardrail.

---

## New files created

```
backend/ml/__init__.py
backend/ml/features.py              Feature pipeline (2.1)
backend/ml/regime.py                Regime classifier (2.2)
backend/ml/model.py                 XGBoost direction model (2.3 + 2.4)
backend/ml/registry.py              Model save/load/list against Neon (2.5)
backend/ml/onnx_models/             Exported ONNX artifacts
  direction_model_NIFTY.onnx
  direction_model_BANKNIFTY.onnx
  regime_classifier_NIFTY.onnx
  regime_classifier_BANKNIFTY.onnx
  + .json metadata files
backend/models/model_registry.py    SQLAlchemy table definition
backend/scripts/train.py            Local training script
backend/scripts/export_onnx.py      ONNX export script
backend/migrations/versions/002_add_model_registry.py
backend/migrations/versions/003_add_model_registry_onnx.py
tests/test_ml_features.py           11 tests — feature pipeline
tests/test_ml_model.py              9 tests  — regime + direction model
tests/test_ml_shadow.py             6 tests  — shadow mode + flag flip
```

## Modified files

```
backend/config/settings.py          + ml_model_version: str = ""
backend/api/routes.py               + _shadow_stats dict, + _ml_shadow(), + /ml/shadow-stats,
                                    + /ml/status, + shadow agreement tracking in get_signal()
backend/.env.example                Updated with all Phase 0–2 env vars
frontend/src/components/SignalCard.jsx  ML panel (shadow/active display)
```

---

## Test counts

| Suite | Tests | Status |
|---|---|---|
| Backend pytest | 61 | All green (1 skipped = DB migration) |
| Frontend vitest | 11 | All green |

---

## Known risks / debt opened

- **In-memory shadow stats** — resets on server restart; no persistence across deployments. Phase 5 should write to `signals` table.
- **ONNX models committed to Git** — ~4 MB total; acceptable for now. If models grow, move to Git LFS or object storage.
- **60-day 5m training window** — yfinance limits sub-hourly data to 60 days. AUC on short windows may be near-random. Phase 3 prep: evaluate daily-timeframe model or paid data source.
- **No reliability diagram PNG** — Brier score is calculated but `docs/ml/reliability_diagram.png` was not generated. Run `python backend/scripts/validate_model.py` after populating `ohlcv_cache` to produce it.
- **Shadow mode has not yet run for ≥ 1 week** — Deploy and observe `GET /api/ml/shadow-stats` for 7 days before treating Phase 2 as fully validated in production.

---

## Handoff to Phase 3

### Context the next agent must know
- `ENABLE_ML_SIGNAL=false` by default; never flip on production account until paper P&L is verified
- `ML_MODEL_VERSION` env var pins a version without DB writes — use it for rollback
- `/api/ml/shadow-stats` shows live agreement rate between rule and ML; check it before flipping `ENABLE_ML_SIGNAL=true`
- ONNX models are loaded from disk first (`backend/ml/onnx_models/`); DB fallback only if disk files missing
- Rule signal (`signal` field in `/api/signal`) is never changed by the ML flag — frontend decides display priority

### Files Phase 3 will touch
- NEW: `backend/risk/engine.py` — SL/TP, trailing stop, daily cutoff, position sizing, kill switch
- NEW: `backend/api/routes.py` — POST `/api/kill-switch`, position cap checks
- `backend/paper_trading/simulator.py` — wire risk engine into enter/exit trade flow
- `backend/models/` — possibly new `positions` table for open position tracking

### "Don't do this" list
- Do NOT flip `ENABLE_ML_SIGNAL=true` before shadow-mode has run ≥ 1 week
- Do NOT import sklearn/xgboost in any Vercel-deployed code path — use ONNX path only
- Do NOT run `backend/scripts/train.py` on Vercel — training is local-only (`/api/train` stub returns 400)
- Do NOT modify the `signal` field in `/api/signal` response shape — frontend depends on it
