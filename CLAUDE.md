# CLAUDE.md — Nifty Options Bot → AI Tradebot

> Claude Code reads this file automatically at the start of every session.
> Keep it current. Full handoff context lives in `docs/AGENT_HANDOFF.md`.

---

## Project identity

- **What it is:** Indian options signal + paper trading app being evolved into a full AI-driven algo-trading platform
- **Owner:** Solo user (Suresh) — no auth, no multi-tenant requirements
- **Instruments:** Nifty 50 + Bank Nifty options (Sensex supported in UI)
- **Broker (Phase 4+):** Zerodha Kite Connect only
- **Working directory:** `c:\Users\Administrator\.cursor\nifty-options-bot`
- **Branch:** `main`

---

## The plan

- **Master plan (frozen 2026-04-21):** `docs/phases/MASTER_PLAN.md` — 6 phases, locked decisions, safety guardrails, TDD criteria. This is the single source of truth for scope.
- **Long-term product vision:** `AlgoTrading_App_Features_and_AgentPrompt.md` — 15 modules. Reference only; build only what MASTER_PLAN.md assigns to the current phase.
- **Full agent handoff:** `docs/AGENT_HANDOFF.md` — complete context for starting fresh sessions.
- **Current phase:** Phase 0 — Foundation Hardening (NOT YET STARTED as of 2026-04-26)
- **Phase 0 kickoff protocol:** `docs/phases/PHASE_0_KICKOFF_PROMPT.md`

---

## Locked decisions (never re-ask)

| Decision | Value |
|---|---|
| Real money | Deferred — paper/sandbox first. Live activation is a manual user step AFTER Phases 0–5 validated. Phase 4 exits on sandbox only. |
| User model | Solo — no auth, no `users` table, no JWT/OTP |
| First broker | Zerodha Kite Connect (Phase 4) |
| ML approach | XGBoost + regime classifier first; deep learning deferred |
| Deployment | Local dev first; Vercel + Render later |
| Deadline | None — quality over speed |

---

## Safety guardrails (every phase, no exceptions)

1. **Additive only** — existing routes, UI, and behavior keep working
2. **Feature flags default OFF** — `ENABLE_ML_SIGNAL`, `ENABLE_LIVE_BROKER`, `ENABLE_AUTO_EXECUTION`
3. **DB migrations are additive** — new tables only; never drop/rename existing
4. **No destructive refactors** — fork into `v2/` and swap via config if needed
5. **Phase ends with green tests + `docs/phases/PHASE_{N}_SUMMARY.md`**
6. **Secrets never in repo** — new env vars go in `backend/.env.example` with placeholder

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI 0.111.0 + Python 3.11, uvicorn, yfinance, httpx, pandas, numpy<2.0, anthropic SDK, SQLite (paper trades) |
| Frontend | React 18.3.1, Zustand, Vite 5, Tailwind CSS 3, lightweight-charts 4.2 |
| CI | GitHub Actions (`.github/workflows/ci.yml`) — frontend build + backend import check |
| Deploy | Vercel (FE static + Python serverless via `api/index.py`) |

Start backend: `cd backend && uvicorn main:app --reload --port 8000`  
Start frontend: `cd frontend && npm run dev` → http://localhost:5173  
Proxy: Vite `/api` → `localhost:8000`

---

## Key files

```
backend/api/routes.py           16 FastAPI endpoints — do NOT break these
backend/main.py                 App factory, CORS
backend/data/market_data.py     OHLCV via yfinance + Yahoo direct + NSE fallback
backend/data/options_chain.py   NSE option chain + synthetic fallback (handles IP blocks)
backend/indicators/engine.py    RSI, MACD, SuperTrend, BB, PCR, confluence score
backend/ai/signal_engine.py     Rule-based BUY_CE / BUY_PE / AVOID signal
backend/ai/budget_optimizer.py  Strike selection + lot sizing
backend/paper_trading/simulator.py  SQLite paper trade tracker
frontend/src/store/index.js     Zustand store — all API calls live here
frontend/src/lib/chartIndicators.js  927-line client-side indicator engine
frontend/src/components/LiveChart.jsx  TradingView-style chart (965 lines)
```

---

## Do NOT touch without phase mandate

- `backend/ai/signal_engine.py`
- `backend/indicators/engine.py`
- Any frontend chart component
- Any existing working API endpoint
- `docs/phases/MASTER_PLAN.md` (propose edit via user approval only)

---

## Phase 0 checklist (in progress)

- [ ] 0.1 PostgreSQL + Alembic (new tables alongside SQLite — do NOT migrate existing data)
- [ ] 0.2 pytest + vitest wired; coverage ≥ 60% on touched files
- [ ] 0.3 pydantic-settings config loader; missing var → named startup error
- [ ] 0.4 Confirm CI green after postcss ESM fix (commit 4315738)
- [ ] 0.5 Structured JSON logging + request-id propagation
- [ ] 0.6 Feature-flag module at `backend/config/feature_flags.py`

New env vars for Phase 0: `DATABASE_URL`, `LOG_LEVEL`, `ENABLE_ML_SIGNAL=false`, `ENABLE_LIVE_BROKER=false`, `ENABLE_AUTO_EXECUTION=false`

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
| NSE API | Blocks non-Indian IPs — always have synthetic fallback |

---

## Uncommitted changes as of 2026-04-26

These exist in the working tree but are NOT committed:
- `backend/api/routes.py` (+20 lines)
- `backend/data/market_data.py` (+107 lines — enhanced fetch logic)
- `docs/phases/MASTER_PLAN.md` (+4 lines)
- `frontend/src/App.jsx` (+7 lines)
- `frontend/src/components/LiveChart.jsx` (+24 lines)
- `frontend/dist/` (rebuilt)
- `AlgoTrading_App_Features_and_AgentPrompt.md` (new untracked file)

Ask the user whether to commit these before starting Phase 0 work.
