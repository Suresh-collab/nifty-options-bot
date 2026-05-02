# CLAUDE.md — Nifty Options Bot → AI Tradebot

> Claude Code reads this file automatically at the start of every session.
> Keep it current. Full handoff context lives in `docs/AGENT_HANDOFF.md`.

---

## Project identity

- **What it is:** Indian options signal + paper trading app — fully evolved into an AI-driven algo-trading platform across 6 phases
- **Owner:** Solo user (Suresh) — no auth, no multi-tenant requirements
- **Instruments:** Nifty 50 + Bank Nifty options (Sensex supported in UI)
- **Broker (Phase 4+):** Zerodha Kite Connect only
- **Working directory:** `c:\Users\Administrator\.cursor\nifty-options-bot`
- **Branch:** `main`

---

## The plan

- **Master plan (frozen 2026-04-21):** `docs/phases/MASTER_PLAN.md` — 6 phases, locked decisions, safety guardrails. Single source of truth for scope.
- **Long-term product vision:** `AlgoTrading_App_Features_and_AgentPrompt.md` — 15 modules. Reference only.
- **Full agent handoff:** `docs/AGENT_HANDOFF.md` — complete context for fresh sessions.
- **Current status:** **All 6 phases CODE-COMPLETE as of 2026-05-02. Production deployment is the next milestone.**

---

## Phase completion status

| Phase | Name | Code | Tests | Deployed |
|---|---|---|---|---|
| 0 | Foundation Hardening | ✅ | ⚠️ Run needed | ❌ |
| 1 | Backtesting Engine | ✅ | ⚠️ Run needed | ❌ |
| 2 | AI/ML Signal Layer | ✅ | ⚠️ Run needed | ❌ |
| 3 | Risk Management Engine | ✅ | ⚠️ Run needed | ❌ |
| 4 | Live Broker Integration | ✅ | ⚠️ Sandbox unverified | ❌ |
| 5 | Real-time & Notifications | ✅ | ⚠️ Run needed | ❌ |
| 6 | Analytics, Scanner, Admin | ✅ | ⚠️ Run needed | ❌ |

⚠️ = Code written and reviewed; formal test run not confirmed green on completed codebase.

---

## What "next step" means

If the user asks **"what's the next step to make this production ready?"**, the answer is the checklist below — in priority order:

### P0 — Blockers (must do before any live use)

1. **Run full test suite** → `cd backend && pytest tests/ -v` + `cd frontend && npm test`
   - Fix any failures before proceeding
   - Target: no failures, coverage ≥ 60% on touched files

2. **Deploy backend to Render or Railway**
   - Vercel 10 s serverless limit kills the market scanner (yfinance batch = 3–8 s)
   - Set all env vars on host (see env section below)
   - Update `CORS` origins in `backend/main.py` for the production domain
   - Update Vite proxy target for production (or use absolute URLs)

3. **Zerodha Kite sandbox end-to-end test**
   - Phase 4 adapter code is complete but never tested against a real Kite sandbox account
   - Steps: get sandbox credentials from Kite developer console → `POST /api/broker/api-keys` → set `ENABLE_LIVE_BROKER=true` + `BROKER_MODE=live` in env → place test order → verify audit log

4. **Confirm GitHub Actions CI green** on current `main` branch

### P1 — Important (for reliable production)

5. **Migrate paper trades to Postgres** — currently SQLite-only; Phase 6 analytics will reset between Render deploys. Add Alembic migration + wire simulator to Postgres.

6. **Persist feature flag overrides** — `set_flag()` is in-memory only; admin panel toggles reset on restart. Add a `flag_overrides` table or write overrides to `.env`.

7. **Wire `ALERT_DEDUP_TTL` to AlertDedup** — `notifications/dedup.py` is hardcoded to 60 s; the setting exists in `config/settings.py` but the dedup singleton never reads it.

8. **Audit `.env.example`** — ensure all Phase 3–6 env vars are present with placeholders and inline comments. Currently missing entries for `BROKER_ENCRYPTION_KEY`, `BROKER_SALT`, `TELEGRAM_BOT_TOKEN`, etc.

### P2 — Polish (nice-to-have before going live)

9. **Expand scanner to 500 tickers** — current implementation covers Nifty 50 (50 tickers). MASTER_PLAN target was 500. Add broader ticker list or use a dedicated screener API.

10. **Telegram webhook** — currently outbound only. Add `POST /api/broker/webhook` to accept Telegram bot commands (`/status`, `/kill`, `/pnl`).

11. **Add Sentry error tracking** — `pip install sentry-sdk[fastapi]`; add `sentry_sdk.init(...)` to `main.py`.

12. **Harden `/health`** — current endpoint returns static JSON; add DB ping + scheduler next-fire-time.

13. **Real-money activation checklist** — before ever flipping `ENABLE_LIVE_BROKER=true` against a real Zerodha account, all of these must be done: (a) sandbox green, (b) paper mode 7-day clean run, (c) daily loss cap verified, (d) kill-switch tested end-to-end, (e) user explicit sign-off.

---

## Locked decisions (never re-ask)

| Decision | Value |
|---|---|
| Real money | Deferred — paper/sandbox first. Live activation is a manual user step only after all P0/P1 items above are done. |
| User model | Solo — no auth, no `users` table, no JWT/OTP |
| First broker | Zerodha Kite Connect (Phase 4) |
| ML approach | XGBoost + regime classifier; deep learning deferred |
| Deployment | Vercel (FE) + Render/Railway (BE) — local dev works now |
| Deadline | None — quality over speed |

---

## Safety guardrails (every phase, no exceptions)

1. **Additive only** — existing routes, UI, and behavior keep working
2. **Feature flags default OFF** — `ENABLE_ML_SIGNAL`, `ENABLE_LIVE_BROKER`, `ENABLE_AUTO_EXECUTION`
3. **DB migrations are additive** — new tables only; never drop/rename existing
4. **No destructive refactors** — fork into `v2/` and swap via config if needed
5. **Secrets never in repo** — new env vars go in `backend/.env.example` with placeholder

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI 0.111.0 + Python 3.11, uvicorn, yfinance, httpx, pandas, numpy<2.0, anthropic SDK |
| Database | SQLite (paper trades, local); Postgres/Neon (OHLCV, signals, audit log, ML registry) |
| Frontend | React 18.3.1, Zustand, Vite 5, Tailwind CSS 3, lightweight-charts 4.2, Recharts 2.12 |
| ML | XGBoost + scikit-learn (local training); ONNX Runtime (Vercel inference) |
| Broker | Zerodha Kite Connect adapter; PaperBrokerAdapter (default) |
| Scheduler | APScheduler 3.10 (daily summary at 3:30 PM IST = 10:00 UTC) |
| Notifications | Telegram bot (httpx); email (aiosmtplib STARTTLS) |
| CI | GitHub Actions — frontend build + backend import check |
| Deploy | Vercel (FE static + Python serverless); Render/Railway (BE long-lived — needed for scanner) |

Start backend: `cd backend && uvicorn main:app --reload --port 8000`
Start frontend: `cd frontend && npm run dev` → http://localhost:5173
Proxy: Vite `/api` → `localhost:8000`

---

## Complete file map

```
backend/
├── main.py                        App factory + CORS + lifespan (P&L poller + APScheduler)
├── requirements.txt               All Python deps (apscheduler already included)
├── .env.example                   Template — all env vars should be here (audit needed)
├── api/
│   ├── routes.py                  34 FastAPI endpoints — do NOT break
│   └── ws.py                      WebSocket /ws/live + broadcast() + background P&L poller
├── ai/
│   ├── signal_engine.py           Rule-based BUY_CE / BUY_PE / AVOID  ← DO NOT TOUCH
│   └── budget_optimizer.py        Strike selection + lot sizing
├── analytics/                     Phase 6
│   └── engine.py                  build_equity_curve, build_drawdown_series, compute_analytics
├── backtesting/                   Phase 1
│   └── engine.py                  Vectorized pandas backtester
├── broker/                        Phase 4
│   ├── interface.py               BrokerAdapter ABC
│   ├── paper_adapter.py           PaperBrokerAdapter (default)
│   ├── zerodha_adapter.py         ZerodhaKiteAdapter (flag-gated)
│   └── crypto.py                  Fernet encrypt/decrypt
├── config/
│   ├── settings.py                pydantic-settings; missing required var → named startup error
│   └── feature_flags.py           is_enabled(), set_flag() in-memory override, all_flags()
├── data/
│   ├── market_data.py             OHLCV via yfinance + NSE fallback  ← DO NOT TOUCH
│   ├── options_chain.py           NSE option chain + synthetic fallback  ← DO NOT TOUCH
│   └── ohlcv_loader.py            Postgres OHLCV load/refresh
├── db/
│   └── base.py                    SQLAlchemy async engine + get_session_factory()
├── indicators/
│   └── engine.py                  RSI, MACD, SuperTrend, BB, EMA, ATR  ← DO NOT TOUCH
├── middleware/
│   └── logging.py                 RequestLoggingMiddleware + JSON logging + request_id
├── migrations/versions/
│   ├── 001_initial_tables.py      trades, signals, backtest_runs, ohlcv_cache, audit_log
│   ├── 002_add_model_registry.py
│   ├── 003_add_model_registry_onnx.py
│   └── 004_add_orders_table.py    broker_orders
├── ml/                            Phase 2
│   ├── features.py                Feature pipeline
│   ├── model.py                   XGBoost direction model
│   ├── registry.py                load_model(), list_models()
│   └── onnx_models/               Pre-exported .onnx + .json files for Vercel inference
├── notifications/                 Phase 5
│   ├── telegram.py                send_message(), send_trade_alert()
│   ├── email.py                   send_daily_summary(), send_critical_alert()
│   └── dedup.py                   AlertDedup (60 s TTL — needs wiring to settings)
├── paper_trading/
│   └── simulator.py               SQLite paper trade CRUD — unchanged from v1
├── risk/                          Phase 3
│   └── engine.py                  SL/TP/trailing, daily cutoff, position sizing, Kelly
├── scanner/                       Phase 6
│   └── engine.py                  Nifty-50 yfinance batch scan, 5-min cache, invalidate_cache()
├── scheduler/                     Phase 6
│   └── jobs.py                    create_scheduler() + daily_summary_job (10:00 UTC)
└── scripts/
    └── train.py                   Local-only ML training (never on Vercel)

frontend/src/
├── App.jsx                        5 tabs: LIVE / BACKTEST / ANALYTICS / SCANNER / ADMIN
├── store/index.js                 Zustand slices: ticker, signal, optimize, trades,
│                                  analytics, scanner, adminFlags, auditLog
└── components/
    ├── LiveChart.jsx              TradingView-style chart (965 lines)  ← DO NOT TOUCH
    ├── AnalyticsTab.jsx           Equity curve (ComposedChart) + drawdown AreaChart + 8-stat strip
    ├── ScannerTab.jsx             2×2 tables + "Scan Now" + WS scanner_update listener
    ├── AdminPanel.jsx             Feature flag toggles + paginated audit log viewer
    ├── BacktestTab.jsx            Phase 1: backtest form + Recharts equity curve
    ├── TradeHistory.jsx           Paper trade log + stats + exit action
    ├── SignalCard.jsx             Signal direction, confidence, entry/SL/TP
    ├── IndicatorGrid.jsx          RSI, MACD, ST, BB, PCR mini-cards
    ├── BudgetOptimizer.jsx        Strike + lot sizing input
    ├── MarketNews.jsx             RSS news feed + keyword sentiment
    ├── MarketStatusBar.jsx        Market open/closed + expiry countdown
    ├── OptionChart.jsx            Option premium chart
    ├── TickerBar.jsx              Scrolling index ticker (NIFTY, SENSEX, etc.)
    ├── TickerSelector.jsx         NIFTY / SENSEX selector + refresh
    └── TradeConfirmModal.jsx      Paper trade confirmation dialog

docs/phases/
├── MASTER_PLAN.md                 The Plan (frozen 2026-04-21) — amend only with user approval
├── PHASE_0_KICKOFF_PROMPT.md
├── PHASE_0_SUMMARY.md            ✅
├── PHASE_1_SUMMARY.md            ✅
├── PHASE_2_SUMMARY.md            ✅
├── PHASE_3_SUMMARY.md            ✅
├── PHASE_4_SUMMARY.md            ✅
├── PHASE_5_SUMMARY.md            ✅
└── PHASE_6_SUMMARY.md            ✅
```

---

## Do NOT touch without explicit mandate

- `backend/ai/signal_engine.py`
- `backend/indicators/engine.py`
- `backend/data/market_data.py` + `options_chain.py`
- Any frontend chart component (`LiveChart.jsx`)
- Any existing working API endpoint
- `docs/phases/MASTER_PLAN.md` (propose edit via user approval only)

---

## Known tech debt (opened across phases)

| Item | Phase | Impact | Fix |
|---|---|---|---|
| Paper trades in SQLite only | P0 | Analytics resets between Render deploys | Migrate to Postgres (additive) |
| Feature flag overrides in-memory | P6 | Admin toggles reset on restart | Add `flag_overrides` Postgres table |
| AlertDedup TTL hardcoded to 60 s | P5 | Setting exists but not wired | `_dedup._ttl = get_settings().alert_dedup_ttl` at startup |
| Scanner covers 50 tickers, not 500 | P6 | Less coverage than MASTER_PLAN target | Expand `_NIFTY50` list or use screener API |
| Scanner timeouts on Vercel | P6 | Broken on Vercel serverless | Move BE to Render/Railway |
| No Telegram webhook | P4 | Bot is outbound-only | Add `POST /api/broker/webhook` |
| WS poller resets `last_payload` on restart | P5 | First broadcast always fires on connect | Persist last payload or add client-side dedup |
| M&M.NS encoded as `M%26M.NS` | P6 | May break if yfinance batch API changes | Watch yfinance changelog |

---

## All environment variables

```bash
# Required
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/nifty_bot
DATABASE_MIGRATION_URL=postgresql://user:pass@host:5432/nifty_bot  # Alembic (plain psycopg2)

# Logging
LOG_LEVEL=INFO

# Feature flags (all OFF by default — real-money safety)
ENABLE_ML_SIGNAL=false
ENABLE_LIVE_BROKER=false
ENABLE_AUTO_EXECUTION=false

# ML
ML_MODEL_VERSION=                   # empty = use latest active; set "v1" to pin

# Risk (Phase 3)
PAPER_TRADING_CAPITAL=100000
DAILY_LOSS_LIMIT_PCT=0.02
DAILY_PROFIT_TARGET_PCT=0.05
MAX_OPEN_POSITIONS=5

# Broker (Phase 4)
BROKER_MODE=paper                   # paper | live
BROKER_ENCRYPTION_KEY=              # Fernet key (generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
BROKER_SALT=                        # random string, per-install

# Notifications (Phase 5)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
ALERT_EMAIL_TO=
ALERT_DEDUP_TTL=60
```

---

## Domain constants

| Constant | Value |
|---|---|
| IST offset | UTC+5:30 |
| Market hours | 9:15 AM – 3:30 PM IST, Mon–Fri |
| NIFTY lot size | 25 |
| BANKNIFTY lot size | 15 |
| SENSEX lot size | 20 |
| NIFTY expiry | Every Thursday |
| BANKNIFTY expiry | Every Wednesday |
| SENSEX expiry | Every Friday |
| CE P&L | (exit − entry) × lots × lot_size |
| PE P&L | (entry − exit) × lots × lot_size |
| NSE API | Blocks non-Indian IPs — always synthetic fallback |
| Scanner cache | 5-minute in-memory TTL |
| Alert dedup | 60 s TTL (default) |
| WS poll | 1 s interval |
| Daily summary | 10:00 UTC (= 3:30 PM IST), Mon–Fri |
