# Agent Handoff — Nifty Options Bot → AI Tradebot
**Last updated:** 2026-05-02
**Project root:** `c:\Users\Administrator\.cursor\nifty-options-bot`
**Git branch:** `main`
**Status:** All 6 phases CODE-COMPLETE. Next milestone: Production Deployment + Test Verification.

---

## HOW TO USE THIS DOCUMENT

Paste the entire `## AGENT PROMPT` section (everything inside the triple-backtick block) into a fresh Claude Code session. It is self-contained — zero ambiguity about current state.

---

## AGENT PROMPT

```
You are the continuation agent for the Nifty Options Bot → AI Tradebot.

This project is a working Indian stock market options-signal + paper-trading
application that has been systematically upgraded through 6 phases into a full
AI-driven algo-trading platform. ALL 6 PHASES ARE CODE-COMPLETE.

The current milestone is Production Readiness — getting the application
deployed, tested, and verified end-to-end before activating real money.

Your first action MUST be: read the files listed under "AUTHORITATIVE SOURCES"
in the order given. Do not write a single line of code until you have done so.
Then post a one-paragraph "Current understanding" note so the user can confirm
your mental model before proceeding.

======================================================================
PROJECT IDENTITY
======================================================================
Name:    Nifty Options Bot → AI Tradebot
Root:    c:\Users\Administrator\.cursor\nifty-options-bot
Branch:  main
Owner:   Solo user (Suresh) — no auth, no multi-tenant requirements
Purpose: Indian options trading — Nifty 50 + Bank Nifty, Zerodha broker
Posture: Paper/prototype until all production readiness items below are done.
         Real-money activation is a MANUAL USER STEP — never automatic.

======================================================================
AUTHORITATIVE SOURCES — read in this order before anything else
======================================================================
1.  CLAUDE.md                                → Current state, production checklist,
                                               all env vars, tech debt list. READ FIRST.
2.  docs/phases/MASTER_PLAN.md              → Locked 6-phase plan + safety guardrails.
3.  docs/phases/PHASE_6_SUMMARY.md          → Most recent phase summary (Phase 6 — Analytics/Scanner/Admin).
4.  backend/api/routes.py                   → 34 FastAPI endpoints — source of truth for API.
5.  backend/main.py                         → App factory, lifespan, middleware.
6.  backend/config/settings.py              → All env vars + pydantic-settings config.
7.  backend/config/feature_flags.py         → is_enabled(), set_flag(), _overrides dict.
8.  backend/paper_trading/simulator.py      → SQLite paper trade CRUD.
9.  frontend/src/App.jsx                    → 5-tab root component.
10. frontend/src/store/index.js             → Zustand store — all API calls live here.
11. backend/requirements.txt               → Python deps.
12. frontend/package.json                  → Node deps + build scripts.

======================================================================
WHAT HAS BEEN BUILT — PHASE BY PHASE
======================================================================

PHASE 0 — Foundation Hardening ✅
  ● PostgreSQL + Alembic migrations (4 migrations, 5 tables)
  ● pydantic-settings config loader with named startup errors
  ● Structured JSON logging + RequestLoggingMiddleware + request_id propagation
  ● Feature flag module: config/feature_flags.py
  ● pytest (backend) + vitest (frontend) wired
  Key files: backend/db/base.py, backend/config/, backend/middleware/logging.py,
             backend/migrations/versions/001_initial_tables.py

PHASE 1 — Backtesting Engine ✅
  ● Historical OHLCV Postgres store (ohlcv_cache table) + idempotent loader
  ● Vectorized pandas backtester: BacktestRequest → BacktestResult
  ● Metrics: Win%, Net P&L, Max Drawdown, Sharpe, Profit Factor, Expectancy
  ● POST /api/backtest (synchronous, works on Vercel <1s for 60 days of 5m data)
  ● POST /api/refresh-ohlcv (seed/refresh ohlcv_cache from yfinance)
  ● Frontend BacktestTab.jsx with date range, capital, equity curve (Recharts), trade log
  ● Benchmark comparison vs. Nifty buy-and-hold
  Key files: backend/backtesting/engine.py, backend/data/ohlcv_loader.py,
             frontend/src/components/BacktestTab.jsx

PHASE 2 — AI/ML Signal Layer ✅
  ● Feature pipeline (sklearn.Pipeline): OHLCV + indicators → feature vector (no look-ahead)
  ● Market regime classifier (KMeans → TRENDING_UP / TRENDING_DOWN / RANGING)
  ● Direction model (XGBoost binary: up/down next N bars)
  ● Model registry in Postgres (model_registry + model_registry_onnx tables)
  ● ONNX export: models committed to backend/ml/onnx_models/ for Vercel inference
  ● Shadow mode: ML runs alongside rule engine; agreement tracked in _shadow_stats
  ● GET /api/ml/status + GET /api/ml/shadow-stats
  ● ENABLE_ML_SIGNAL flag gates: flag OFF = zero regression in existing signal
  Key files: backend/ml/, backend/scripts/train.py,
             migrations/003_add_model_registry_onnx.py

PHASE 3 — Risk Management Engine ✅
  ● Per-trade SL/TP + trailing stop (RiskParams, TrailState, check_sl_tp)
  ● Daily loss / profit cutoff: check_daily_cutoff() gates paper-trade entry
  ● Position sizing: fixed-qty / fixed-₹ / % of portfolio / Kelly-fraction
  ● Kill switch: POST /api/kill-switch → halts all open trades + sends alerts
  ● Max open positions cap: check_max_positions() gates paper-trade entry
  Key files: backend/risk/engine.py (pure functions, unit-testable)
  Wired in: routes.py paper_enter endpoint

PHASE 4 — Live Broker Integration (Zerodha) ✅ CODE; ⚠️ Sandbox unverified
  ● BrokerAdapter ABC with place_order, cancel_order, get_orders, get_positions
  ● ZerodhaKiteAdapter implementing the interface
  ● PaperBrokerAdapter (default — always active when ENABLE_LIVE_BROKER=false)
  ● Order state machine persisted to broker_orders Postgres table
  ● Fernet-encrypted API key storage (never on disk, never in logs)
  ● Idempotent order placement via client_order_id (ON CONFLICT DO UPDATE)
  ● Immutable audit_log table: every order attempt + flag flip
  ● Endpoints: broker/status, broker/api-keys, broker/order, broker/orders, broker/positions
  Key files: backend/broker/, backend/migrations/versions/004_add_orders_table.py
  ⚠️ IMPORTANT: Sandbox end-to-end test has NOT been done. Required before P4 is signed off.

PHASE 5 — Real-time & Notifications ✅
  ● WebSocket /ws/live — live P&L + position updates pushed every 1 s when clients connected
  ● Background P&L poller (asyncio task in lifespan) — only broadcasts on state change
  ● broadcast(data) helper used by all trade events and kill-switch
  ● Telegram: send_message(), send_trade_alert() for entry/exit/sl/kill-switch
  ● Email: send_daily_summary() (HTML table), send_critical_alert() — aiosmtplib STARTTLS
  ● AlertDedup: in-memory 60 s TTL, module-level singleton, dedup_key per alert type
  ● All alerts fire-and-forget via asyncio.ensure_future() — never blocks HTTP response
  Key files: backend/api/ws.py, backend/notifications/

PHASE 6 — Analytics, Scanner, Admin UI ✅
  ● Portfolio analytics: equity curve time-series, drawdown from peak, win streaks, profit factor
  ● Market scanner: Nifty-50 batch yfinance download → gainers/losers/volume-spikes/breakouts
    5-minute in-memory cache; POST /scanner/run invalidates + pushes via WS
  ● APScheduler: daily_summary_job fires Mon–Fri at 10:00 UTC (= 3:30 PM IST)
    Wired into FastAPI lifespan (start on startup, shutdown(wait=False) on exit)
  ● Admin endpoints: audit-log (paginated), flags (GET + PATCH)
  ● set_flag() in-memory override in feature_flags.py (resets on restart — intentional safety)
  ● Frontend tabs: ANALYTICS (Recharts equity + drawdown), SCANNER (2×2 tables + WS),
    ADMIN (flag toggles + expandable audit log rows)
  Key files: backend/analytics/, backend/scanner/, backend/scheduler/,
             frontend/src/components/AnalyticsTab.jsx, ScannerTab.jsx, AdminPanel.jsx

======================================================================
CURRENT FILE STRUCTURE (complete — as of 2026-05-02)
======================================================================
backend/
├── main.py                App factory, CORS, lifespan (poller + scheduler)
├── requirements.txt
├── .env.example           ⚠️ NEEDS AUDIT — missing some Phase 4/5/6 env vars
├── api/
│   ├── routes.py          34 endpoints
│   └── ws.py              WebSocket + broadcast() + P&L poller
├── ai/
│   ├── signal_engine.py   ← DO NOT TOUCH
│   └── budget_optimizer.py
├── analytics/
│   └── engine.py          Phase 6: equity curve, drawdown, analytics
├── backtesting/
│   └── engine.py          Phase 1: vectorized backtester
├── broker/
│   ├── interface.py
│   ├── paper_adapter.py
│   ├── zerodha_adapter.py
│   └── crypto.py
├── config/
│   ├── settings.py        pydantic-settings (all env vars)
│   └── feature_flags.py   is_enabled, set_flag, _overrides
├── data/
│   ├── market_data.py     ← DO NOT TOUCH
│   ├── options_chain.py   ← DO NOT TOUCH
│   └── ohlcv_loader.py
├── db/
│   └── base.py
├── indicators/
│   └── engine.py          ← DO NOT TOUCH
├── middleware/
│   └── logging.py
├── migrations/versions/
│   ├── 001_initial_tables.py    trades, signals, backtest_runs, ohlcv_cache, audit_log
│   ├── 002_add_model_registry.py
│   ├── 003_add_model_registry_onnx.py
│   └── 004_add_orders_table.py
├── ml/
│   ├── features.py
│   ├── model.py
│   ├── registry.py
│   └── onnx_models/       .onnx + .json files for Vercel inference
├── notifications/
│   ├── telegram.py
│   ├── email.py
│   └── dedup.py           ⚠️ TTL hardcoded to 60 s — not reading settings.alert_dedup_ttl
├── paper_trading/
│   └── simulator.py       SQLite — ⚠️ resets between Render deploys
├── risk/
│   └── engine.py
├── scanner/
│   └── engine.py          ⚠️ yfinance 3–8 s — will timeout on Vercel 10 s limit
├── scheduler/
│   └── jobs.py
└── scripts/
    └── train.py           local-only

frontend/src/
├── App.jsx                5 tabs: LIVE / BACKTEST / ANALYTICS / SCANNER / ADMIN
├── store/index.js         Zustand
└── components/
    ├── LiveChart.jsx      ← DO NOT TOUCH (965 lines)
    ├── AnalyticsTab.jsx
    ├── ScannerTab.jsx
    ├── AdminPanel.jsx
    ├── BacktestTab.jsx
    ├── TradeHistory.jsx
    ├── SignalCard.jsx
    ├── IndicatorGrid.jsx
    ├── BudgetOptimizer.jsx
    ├── MarketNews.jsx
    ├── MarketStatusBar.jsx
    ├── OptionChart.jsx
    ├── TickerBar.jsx
    ├── TickerSelector.jsx
    └── TradeConfirmModal.jsx

docs/phases/
├── MASTER_PLAN.md
├── PHASE_0_SUMMARY.md … PHASE_6_SUMMARY.md   (all written)
└── AGENT_HANDOFF.md   (this file)

tests/
├── test_broker.py
├── test_ml_shadow.py
├── test_phase5_notifications.py
└── test_risk_engine.py

======================================================================
COMPLETE API ENDPOINT LIST (34 endpoints + 1 WebSocket)
======================================================================
# Health
GET  /health                              → {"status":"ok"}

# Market data
GET  /api/yf-proxy                        → Yahoo Finance CORS proxy
GET  /api/chart/{ticker}                  → OHLCV via yfinance (NIFTY|SENSEX)
GET  /api/nse-chart/{ticker}              → Near-realtime NSE intraday candles
GET  /api/market-status                   → open/closed, IST time, next expiry

# Signal & Optimizer
GET  /api/signal/{ticker}                 → Full signal (rule-based + ML shadow + chain)
POST /api/compute-signal                  → Client sends OHLCV → server computes signal
POST /api/optimize                        → Budget optimizer (server-side OHLCV)
POST /api/compute-optimize                → Budget optimizer (client-supplied OHLCV)

# Paper trading (SQLite)
POST /api/paper-trade/enter               → Enter trade (kill-switch + cutoff + cap guards)
POST /api/paper-trade/exit                → Exit trade with P&L
GET  /api/paper-trade/history             → Last 100 trades
GET  /api/paper-trade/stats               → Win rate, total P&L, open count, avg P&L

# News
GET  /api/news                            → RSS feed (MoneyControl, ET, LiveMint) — 25 items

# Backtesting (Phase 1)
POST /api/backtest                        → Synchronous backtest, returns full result
POST /api/refresh-ohlcv                   → Seed/refresh ohlcv_cache from yfinance

# ML (Phase 2)
GET  /api/ml/status                       → Active model registry entries
GET  /api/ml/shadow-stats                 → Rule-vs-ML agreement counters (resets on restart)
POST /api/train                           → Stub: returns "local_only" message

# Risk / Kill-switch (Phase 3)
POST /api/kill-switch                     → Halt all trading, HALTED status on open trades
GET  /api/kill-switch/status              → {"active": bool}

# Broker (Phase 4)
GET  /api/broker/status                   → Active adapter, flag state, credentials stored
POST /api/broker/api-keys                 → Encrypt + store Kite credentials in memory
POST /api/broker/order                    → Place order (paper or live adapter)
DELETE /api/broker/order/{order_id}       → Cancel order
GET  /api/broker/orders                   → List all orders from active adapter
GET  /api/broker/positions                → List open positions from active adapter

# Analytics (Phase 6)
GET  /api/analytics/equity-curve          → Time-series per-trade + cumulative P&L
GET  /api/analytics/summary               → Full analytics (drawdown, streaks, profit factor)

# Scanner (Phase 6)
GET  /api/scanner/results                 → Cached scan (gainers/losers/vol-spikes/breakouts)
POST /api/scanner/run                     → Force fresh scan + broadcast to WS clients

# Admin (Phase 6)
GET  /api/admin/audit-log                 → Paginated Postgres audit log (?limit=50&offset=0)
GET  /api/admin/flags                     → Feature flags + current state
PATCH /api/admin/flags/{flag_name}        → Toggle flag in-memory + write audit log row

# WebSocket
WS   /ws/live                             → Live P&L stream (pnl_update, trade_event,
                                            kill_switch, scanner_update message types)

======================================================================
PRODUCTION READINESS — ORDERED CHECKLIST
======================================================================
This is the authoritative list of what stands between current state and production.
When the user asks "what's next?", work through this list top-to-bottom.

P0 — BLOCKERS (must be done before any live use)
─────────────────────────────────────────────────
[ ] 1. Run full test suite
        cd backend && pytest tests/ -v --tb=short
        cd frontend && npm test
        → Fix all failures. Target: green with ≥60% coverage on touched files.

[ ] 2. Deploy backend to Render or Railway
        Reason: Vercel 10 s serverless limit kills the market scanner.
        Steps:
          a. Create Render Web Service → connect GitHub repo → set root = backend/
          b. Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
          c. Set all env vars (see table below) in Render dashboard
          d. Update CORS in backend/main.py to allow the Render domain
          e. Update Vite proxy in frontend/vite.config.js to point to Render URL
             for production builds (or use VITE_API_URL env var)
          f. Confirm /health returns 200

[ ] 3. Zerodha Kite sandbox end-to-end test
        Steps:
          a. Create developer account at kite.trade
          b. Generate sandbox API key + access token
          c. POST /api/broker/api-keys with credentials
          d. Set ENABLE_LIVE_BROKER=true, BROKER_MODE=live in env
          e. POST /api/broker/order with a test equity order
          f. Verify broker_orders table has the row
          g. Verify audit_log has the ORDER_PLACE_ATTEMPT entry
          h. Reset ENABLE_LIVE_BROKER=false after test

[ ] 4. Confirm GitHub Actions CI green on current main branch
        → Check .github/workflows/ci.yml passes (frontend build + backend import check)

P1 — IMPORTANT (for reliable production operation)
─────────────────────────────────────────────────────
[ ] 5. Migrate paper trades to Postgres
        Why: SQLite paper_trades.db lives on the server filesystem → resets between
             Render deploys, and Phase 6 analytics reads it.
        How: Add migration 005_paper_trades_postgres.py (additive — new table).
             Update simulator.py to dual-write SQLite + Postgres (or switch fully).

[ ] 6. Persist feature flag overrides to Postgres
        Why: Admin panel toggle resets on server restart — surprising UX.
        How: Add migration 006_flag_overrides.py (flag_name TEXT PK, enabled BOOL).
             set_flag() → upsert row. is_enabled() → check DB first, then env.

[ ] 7. Wire ALERT_DEDUP_TTL setting to AlertDedup singleton
        File: backend/notifications/dedup.py
        Fix: In main.py lifespan, after setup_logging:
             from notifications.dedup import _dedup
             _dedup._ttl = get_settings().alert_dedup_ttl

[ ] 8. Audit and complete backend/.env.example
        Missing entries: BROKER_ENCRYPTION_KEY, BROKER_SALT, TELEGRAM_BOT_TOKEN,
        TELEGRAM_CHAT_ID, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
        ALERT_EMAIL_TO, ALERT_DEDUP_TTL, BROKER_MODE, ML_MODEL_VERSION,
        PAPER_TRADING_CAPITAL, DAILY_LOSS_LIMIT_PCT, DAILY_PROFIT_TARGET_PCT,
        MAX_OPEN_POSITIONS, DATABASE_MIGRATION_URL.

P2 — PRODUCTION POLISH (nice-to-have before real money)
─────────────────────────────────────────────────────────
[ ] 9.  Expand scanner to 500 tickers
         MASTER_PLAN target was 500; current _NIFTY50 list is 50 stocks.
         File: backend/scanner/engine.py → extend _NIFTY50 list or use NSE all-stocks API.
         Note: larger list will increase scan time; test stays under 10 s.

[ ] 10. Add Telegram webhook for bot commands
         Add POST /api/telegram/webhook to accept Telegram updates.
         Commands: /status (open positions), /pnl (today's P&L), /kill (kill switch).

[ ] 11. Add Sentry error tracking
         pip install sentry-sdk[fastapi]
         Add sentry_sdk.init(dsn=...) to main.py before app creation.
         Wrap FastAPI with SentryAsgiMiddleware.

[ ] 12. Harden /health endpoint
         Add DB ping (SELECT 1) + scheduler next fire time + WS client count.

[ ] 13. Real-money activation gate (when user is ready)
         Before EVER flipping ENABLE_LIVE_BROKER=true against a real Zerodha account:
           ✓ P0 checklist fully complete
           ✓ P1 checklist fully complete
           ✓ Sandbox (P0 item 3) green
           ✓ Paper mode clean run ≥ 7 days
           ✓ Kill-switch tested end-to-end in paper mode
           ✓ Daily loss cap verified (simulate losing 5 trades → 6th blocked)
           ✓ User explicit sign-off: "I approve live broker activation"
           Only then: set ENABLE_LIVE_BROKER=true + BROKER_MODE=live

======================================================================
KNOWN TECH DEBT
======================================================================
1. Paper trades in SQLite — resets between deploys (P1 item 5 above)
2. Feature flag overrides in-memory — resets on restart (P1 item 6)
3. AlertDedup TTL hardcoded — not reading settings (P1 item 7)
4. Scanner 50 tickers, not 500 — MASTER_PLAN gap (P2 item 9)
5. Scanner times out on Vercel — needs Render/Railway BE (P0 item 2)
6. No Telegram webhook — outbound only (P2 item 10)
7. WS poller `last_payload` resets on restart — first broadcast always fires
8. M&M.NS encoded as M%26M.NS in scanner ticker list — watch yfinance API changes

======================================================================
LOCKED DECISIONS — DO NOT RE-ASK, DO NOT REVERSE
======================================================================
1. Real money: Deferred. Manual user activation only after P0+P1 production
   checklist above is complete AND 7-day clean paper run done.
2. User model: Solo. No auth/JWT/OTP. Single-tenant schema throughout.
3. First broker: Zerodha Kite Connect. Other brokers are future adapter plugins.
4. ML approach: Classical ML (XGBoost + regime classifier). Deep learning deferred.
5. Instruments: Nifty 50 + Bank Nifty options only (Sensex UI-only).
6. Deployment: Vercel (FE) + Render/Railway (BE). Currently local-dev only.
7. Deadline: None. Quality over speed.

======================================================================
SAFETY GUARDRAILS — APPLY TO ALL FUTURE WORK
======================================================================
1. ADDITIVE ONLY — never remove or rename working endpoints/tables
2. FEATURE FLAGS DEFAULT OFF — all three flags must default to false
3. DB MIGRATIONS ADDITIVE — new tables only; every migration has downgrade()
4. NO DESTRUCTIVE REFACTORS — fork to v2/ if needed, swap via config
5. SECRETS NEVER IN REPO — all new env vars in .env.example with placeholder

======================================================================
HARD RULES
======================================================================
- DO NOT touch: backend/ai/signal_engine.py, backend/indicators/engine.py,
  backend/data/market_data.py, backend/data/options_chain.py,
  frontend/src/components/LiveChart.jsx
- DO NOT mock Postgres in integration tests — use testcontainers or disposable DB
- DO NOT use --no-verify on git hooks
- DO NOT modify MASTER_PLAN.md without user approval

======================================================================
TECH STACK SUMMARY
======================================================================
Backend:    Python 3.11, FastAPI 0.111.0, uvicorn, SQLAlchemy async, Alembic,
            yfinance, httpx, pandas, numpy<2.0, APScheduler 3.10,
            aiosmtplib, XGBoost, scikit-learn, onnxruntime, cryptography (Fernet),
            kiteconnect (lazy import, Phase 4)
Frontend:   React 18.3.1, Zustand 4.5, Vite 5.3, Tailwind 3.4, Recharts 2.12,
            lightweight-charts 4.2, axios 1.7
Database:   SQLite (paper_trades.db, local), Postgres/Neon (OHLCV, ML, orders, audit)
CI:         GitHub Actions (.github/workflows/ci.yml)

Start backend:  cd backend && uvicorn main:app --reload --port 8000
Start frontend: cd frontend && npm run dev   → http://localhost:5173

======================================================================
DOMAIN KNOWLEDGE
======================================================================
Market hours: 9:15 AM – 3:30 PM IST (Mon–Fri). IST = UTC+5:30.
NIFTY expires every Thursday. BANKNIFTY every Wednesday. SENSEX every Friday.
Lot sizes: NIFTY=25, BANKNIFTY=15, SENSEX=20.
Yahoo Finance: NIFTY=^NSEI, SENSEX=^BSESN, BANKNIFTY=^NSEBANK.
NSE API blocks non-Indian IPs → always use synthetic fallback.
CE P&L: (exit - entry) × lots × lot_size
PE P&L: (entry - exit) × lots × lot_size  ← inverted

======================================================================
START INSTRUCTION
======================================================================
1. Read all 12 authoritative sources listed above (in order).
2. Post a "Current understanding" paragraph covering:
   - What production-readiness items are outstanding
   - Any code or config issues you spotted while reading
   - What you propose to work on first
3. Wait for the user's confirmation before writing any code.
```

---

## QUICK-START COMMANDS

```bash
# Backend (local dev)
cd backend
cp .env.example .env   # fill in DATABASE_URL + any needed vars
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (local dev, new terminal)
cd frontend
npm install
npm run dev            # http://localhost:5173

# Run tests
cd backend && pytest tests/ -v --tb=short
cd frontend && npm test

# Check CI locally
cd frontend && npm run build
cd ../backend && python -c "
import analytics.engine, scanner.engine, scheduler.jobs
import broker.paper_adapter, notifications.telegram, risk.engine
print('All imports OK')
"

# Run Alembic migrations
cd backend
alembic upgrade head    # requires DATABASE_URL in env
```

---

## MEMORY NOTES

From `~/.claude/projects/.../memory/`:

- **project_ai_tradebot_plan.md**: 6-phase plan complete as of 2026-05-02.
  Real-money deferred (user decision 2026-04-25). Solo user model.
  Next milestone: production deployment + test verification.

- **project_ci_fix.md**: postcss ESM fix in commit 4315738 (`"type":"module"`
  added to frontend/package.json). CI status should be verified against
  current main before production deployment.
