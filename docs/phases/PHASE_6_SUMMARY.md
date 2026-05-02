# Phase 6 Summary — Analytics, Scanner, Admin UI

**Completed:** 2026-05-02  
**Branch:** main  
**Scope:** Pure code additions — no new external credentials required.

---

## What was built

### 6.1 Portfolio Analytics (`backend/analytics/engine.py`)

Pure-function module consumed by two new endpoints:

| Endpoint | Description |
|---|---|
| `GET /api/analytics/equity-curve` | Time-series of per-trade P&L + cumulative P&L sorted by exit time |
| `GET /api/analytics/summary` | Full analytics: equity curve, drawdown series, win rate, streaks, profit factor |

**Functions:**
- `build_equity_curve(trades)` — closed trades → sorted time-series with cumulative P&L
- `build_drawdown_series(equity_curve)` — drawdown % from rolling peak
- `compute_analytics(trades)` — combined output including win streaks and profit factor
- `_max_streak(pnls, win)` — helper for consecutive win/loss streak counting

### 6.2 Market Scanner (`backend/scanner/engine.py`)

Batched yfinance download (single HTTP call, 50 Nifty-50 tickers, 25 days of daily data).

| Endpoint | Description |
|---|---|
| `GET /api/scanner/results` | Cached scan results (TTL 5 minutes) |
| `POST /api/scanner/run` | Force fresh scan, update cache, push to WS clients |

**Categories returned:**
- `gainers` — top 10 day-change% > 0
- `losers` — top 10 day-change% < 0
- `volume_spikes` — vol_ratio ≥ 2× 5-day average
- `breakouts` — within 1% of 20-day high (breakout) or 20-day low (breakdown)

**Performance:** Typically 3–8 s for 50 tickers via yfinance batch mode.  
**Cache:** 5-minute in-memory TTL; `invalidate_cache()` used by `POST /scanner/run`.

### 6.3 Admin Panel (`backend/api/routes.py` additions)

| Endpoint | Description |
|---|---|
| `GET /api/admin/audit-log` | Paginated audit log from Postgres (`limit`, `offset` params) |
| `GET /api/admin/flags` | All feature flags + current state (env + in-memory overrides) |
| `PATCH /api/admin/flags/{flag_name}` | Toggle flag in-memory; writes `FLAG_TOGGLE` audit log row |

**Feature flag enhancement (`backend/config/feature_flags.py`):**
- Added `_overrides: dict` — in-memory state set by admin UI, takes precedence over env/settings
- Added `set_flag(flag, value)` — sets override; validated against known flag names
- `all_flags()` now routes through `is_enabled()` so overrides are reflected

### 6.4 Scheduler — daily summary (`backend/scheduler/`)

- `create_scheduler()` returns APScheduler `AsyncIOScheduler` with one job
- `daily_summary_job()` — sends email P&L summary via `notifications.email.send_daily_summary()`
- Schedule: `mon-fri` at `10:00 UTC` (= 3:30 PM IST)
- `apscheduler` was already in `requirements.txt` (3.10.4)
- Wired into FastAPI lifespan in `main.py` (start on startup, `shutdown(wait=False)` on exit)

---

## Frontend additions

### New components

| File | Description |
|---|---|
| `AnalyticsTab.jsx` | Equity curve (ComposedChart: bar per trade + cumulative line) + drawdown AreaChart + 8-stat card strip |
| `ScannerTab.jsx` | 2×2 grid: gainers, losers, volume spikes, breakouts tables. "Scan Now" button + WS `scanner_update` subscription |
| `AdminPanel.jsx` | Feature flag toggles (Toggle switch component) + paginated audit log with expandable payload rows |

### Store additions (`store/index.js`)

New Zustand slices:
- `analyticsData / analyticsLoading / fetchAnalytics()`
- `scannerData / scannerLoading / fetchScannerResults() / runScanner()`
- `adminFlags / adminFlagsLoading / fetchAdminFlags() / toggleAdminFlag(name, enabled)`
- `auditLog / auditLogLoading / fetchAuditLog(offset, limit)`

### App.jsx

Added three tabs to the nav bar: `ANALYTICS`, `SCANNER`, `ADMIN`. The `live` and `backtest` tabs are unchanged.

---

## Architecture decisions

| ADR | Decision |
|---|---|
| ADR-028 | Scanner uses yfinance batch download (single call) rather than per-ticker requests — keeps latency under 10 s for 50 tickers |
| ADR-029 | Scanner cache is in-memory (not Redis) — acceptable for a solo-user local deployment; `POST /scanner/run` is the cache-busting mechanism |
| ADR-030 | Feature flag overrides are in-memory only — intentional; resets on restart as a safety property for live-trading flags |
| ADR-031 | Drawdown chart Y-axis is `reversed` so 0% is at top and deeper drawdown goes down visually |
| ADR-032 | APScheduler `AsyncIOScheduler` (not `BackgroundScheduler`) so jobs run on the same event loop as FastAPI — avoids cross-thread DB calls |

---

## Known limitations / tech debt opened

1. **Scanner on Vercel** — yfinance requires network egress; the scanner will time out on Vercel's 10 s serverless limit for 50 tickers. Move to a long-lived backend (Render/Railway) before using in production.
2. **Equity curve from SQLite only** — paper trades are not persisted to Postgres, so the analytics endpoint reads from SQLite. Phase 7 should migrate trades to Postgres for richer cross-session queries.
3. **Flag overrides reset on restart** — expected behavior (safety guardrail) but not persisted to DB. A future phase could store overrides in Postgres.
4. **M&M.NS URL encoding** — yfinance symbol uses `%26` encoding (`M%26M.NS`) in the ticker list. If batch download behavior changes, this may need adjustment.

---

## Test targets (TDD criteria)

- `analytics.engine.build_equity_curve` — verify sorted order, cumulative calculation, empty list
- `analytics.engine.build_drawdown_series` — verify peak tracking, zero drawdown when always going up
- `analytics.engine.compute_analytics` — verify empty trades returns all-zero struct
- `scanner.engine.run_scan` — verify cache TTL logic, fallback structure on yfinance error
- `feature_flags.set_flag` — verify override takes precedence over settings, rejects unknown flags
- `POST /api/admin/flags/{flag_name}` — 400 on unknown flag, 200 + audit row on valid flag
- `GET /api/analytics/summary` — 200 with expected keys when trades exist
- `GET /api/scanner/results` — 200, result has `gainers/losers/volume_spikes/breakouts` keys
