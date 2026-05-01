# Phase 1 Summary — Backtesting Engine
**Status:** Complete
**Duration:** 2026-05-01
**Completed by:** Claude Sonnet 4.6 agent session

---

## Scope delivered

- [x] Import style fix — all `from backend.*` imports in backend source changed to short-style; `sys.path.insert` in `main.py` ensures server works from `backend/` dir
- [x] 1.1 OHLCV loader — `backend/data/ohlcv_loader.py` fetches 5m (60 days) + 1d (2 years) for NIFTY and BANKNIFTY via yfinance; idempotent upsert into `ohlcv_cache`
- [x] 1.2 Vectorized backtester — `backend/backtesting/engine.py`; pre-computes RSI, MACD, SuperTrend, BB on full DataFrame; signals using same scoring logic as rule engine
- [x] 1.3 Metrics module — `backend/backtesting/metrics.py`; Win%, Net P&L, Max Drawdown, Sharpe (annualised, ddof=1), Profit Factor, Expectancy
- [x] 1.4 API endpoints — `POST /api/backtest` (async background task, in-memory + DB store) + `GET /api/backtest/{id}`
- [x] 1.5 Frontend Backtest tab — `frontend/src/components/BacktestTab.jsx`; date picker, capital, SL%, run button, polling, metrics grid, equity curve (Recharts)
- [x] 1.6 Benchmark — buy-and-hold Nifty overlay on equity curve chart

---

## TDD criteria results

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1.1 | Idempotent loader (re-run doesn't duplicate rows) | ✅ pass | `ON CONFLICT DO NOTHING` in `_upsert_batch` |
| 1.2 | Backtester produces deterministic results | ✅ pass | `tests/test_backtest_engine.py::test_run_backtest_deterministic` |
| 1.3 | Known P&L series → Sharpe matches reference to 4 decimals | ✅ pass | `tests/test_metrics.py::test_sharpe_ratio_matches_reference` (ref=9.1959) |
| 1.4 | POST run → poll GET → status=complete, result JSON shape locked | ✅ pass | `tests/test_backtest_api.py::test_post_poll_get_complete` |
| 1.5 | Component renders form + results with mocked API | ✅ pass | `frontend/src/test/BacktestTab.test.jsx` |
| 1.6 | Benchmark curve rendered alongside strategy curve | ✅ pass | `EquityCurve` component renders both lines |

---

## Architecture decisions

- **ADR-005: In-memory store for backtest runs** — `_backtest_store: dict` in routes.py. Avoids Neon round-trip for the poll response. DB write is best-effort (does not fail the task if DB write fails). Phase 2+ can swap to full DB-backed store.
- **ADR-006: 60-day 5m window** — yfinance hard limit for sub-hourly data is 60 days. Architecture is identical to a 2-year store; data source upgrade happens in Phase 2 prep when a paid data provider is wired.
- **ADR-007: ATM delta approximation for P&L** — Backtester uses `DELTA_FACTOR=0.5` to convert underlying point moves to option P&L. Phase 2 will add actual option chain price simulation.
- **ADR-008: Short imports throughout backend** — All `from backend.X` replaced with `from X` in backend source files. `sys.path.insert` in `main.py` ensures this works when uvicorn runs from `backend/` dir. Tests use `pythonpath = . backend` (pytest.ini).

---

## New files created

```
backend/data/ohlcv_loader.py             yfinance fetch + DB upsert + load_ohlcv()
backend/backtesting/__init__.py
backend/backtesting/engine.py            vectorized backtester, benchmark_buy_hold
backend/backtesting/metrics.py           win_rate, net_pnl, sharpe, drawdown, etc.
frontend/src/components/BacktestTab.jsx  full Backtest UI tab
tests/test_metrics.py                    9 unit tests
tests/test_backtest_engine.py            8 unit tests (no DB, synthetic data)
tests/test_backtest_api.py               5 integration tests
frontend/src/test/BacktestTab.test.jsx   5 component tests
```

## Modified files

```
backend/main.py                    + sys.path.insert, short imports
backend/config/__init__.py         short imports
backend/config/feature_flags.py   short imports
backend/db/base.py                 short imports
backend/models/__init__.py         short imports
backend/models/*.py (5 files)      short imports
backend/migrations/env.py          + backend/ to sys.path, short imports
backend/api/routes.py              + BacktestRequest, POST /backtest, GET /backtest/{id}
frontend/src/App.jsx               + LIVE/BACKTEST tab navigation, BacktestTab import
tests/conftest.py                  short imports
tests/test_feature_flags.py        short imports
tests/test_logging.py              short imports
tests/test_migrations.py           short imports
frontend/src/test/setup.js         + ResizeObserver polyfill for jsdom
```

---

## Test counts

| Suite | Tests | Status |
|---|---|---|
| Backend pytest | 36 | All green |
| Frontend vitest | 11 | All green |

---

## Known risks / debt opened

- **In-memory backtest store is not persisted** — server restart loses all run history. Phase 2 should migrate to full DB-backed store using `backtest_runs` table.
- **60-day data limit** — 5m backtest window is only 60 days. This is a yfinance limitation. For longer backtests, Phase 2 needs an alternative data source.
- **No actual option pricing** — P&L uses `DELTA_FACTOR=0.5` approximation. Real option Greeks (IV, delta, theta) needed for accurate simulation.
- **SuperTrend has a Python loop** — `_supertrend` in `indicators/engine.py` uses a Python for-loop (not vectorized). Performance acceptable for 60 days of 5m data (~700 bars) but would be slow for multi-year daily.

---

## Handoff to Phase 2

### Context the next agent must know
- Short imports everywhere in `backend/` — never write `from backend.X import Y` in source files (only OK in test files or scripts that import from project root with `backend.` prefix)
- `_backtest_store` in `backend/api/routes.py` is module-level in-memory — not persisted across server restarts
- `load_ohlcv(symbol, interval, start, end, session)` is the DB query function; `refresh_ohlcv()` is the yfinance fetcher
- BacktestTab polls `/api/backtest/{id}` every 1000ms until `status === 'COMPLETE'` or `'ERROR'`
- `ResizeObserver` polyfill is in `frontend/src/test/setup.js` — needed for Recharts in jsdom
- `vi.runAllTimersAsync()` inside `await act(async () => {...})` is the reliable pattern for testing async `setInterval` callbacks with vitest fake timers

### Files Phase 2 will touch
- `backend/backtesting/engine.py` — add ML signal path (feature-flagged)
- `backend/api/routes.py` — backtest store → Postgres `backtest_runs` table
- New: `backend/ai/ml_engine.py` — XGBoost classifier
- New: `backend/ai/feature_builder.py` — feature engineering from OHLCV

### "Don't do this" list
- Do NOT write `from backend.config.settings import ...` in backend source files — use `from config.settings import ...`
- Do NOT add `ResizeObserver` mock directly in tests — it's global in `setup.js`
- Do NOT run `vi.runAllTimers()` (sync version) for async timer callbacks — use `vi.runAllTimersAsync()`
- Do NOT advance `sys.path` in test files — `pytest.ini`'s `pythonpath = . backend` handles it
