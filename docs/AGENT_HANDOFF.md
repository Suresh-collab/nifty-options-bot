# Agent Handoff Prompt — Nifty Options Bot → AI Tradebot
**Generated:** 2026-04-26  
**Project root:** `c:\Users\Administrator\.cursor\nifty-options-bot`  
**Git branch:** `main`  
**Current phase:** Phase 0 — Foundation Hardening (NOT YET STARTED — ready to begin)

---

## HOW TO USE THIS DOCUMENT

Paste the entire contents of the `## AGENT PROMPT` section (starting with the line `You are the continuation agent...`) into a fresh Claude Code session. Read everything below it verbatim — it contains zero ambiguity about the state of the project.

---

## AGENT PROMPT

```
You are the continuation agent for the Nifty Options Bot → AI Tradebot upgrade.
This project is a working Indian stock market options-signal and paper-trading
application being systematically evolved into a full AI-driven algo-trading
platform, following a locked 6-phase master plan.

Your first action MUST be: read every file listed under
"AUTHORITATIVE SOURCES" in the order given. Do not write a single line of
code until you have done so. Then post a one-paragraph "Understanding" note
so the user can verify you have the right mental model before proceeding.

======================================================================
PROJECT IDENTITY
======================================================================
Name:    Nifty Options Bot → AI Tradebot
Root:    c:\Users\Administrator\.cursor\nifty-options-bot
Branch:  main
Owner:   Solo user (Suresh) — no auth, no multi-tenant requirements
Purpose: Indian options trading — Nifty 50 + Bank Nifty, Zerodha broker (Phase 4+)
Posture: Paper/prototype FIRST. Real-money activation is a manual user step
         taken ONLY after Phases 0–5 are fully validated in paper mode.

======================================================================
AUTHORITATIVE SOURCES — read in this order, completely, before anything else
======================================================================
1.  docs/phases/MASTER_PLAN.md
        → Frozen 2026-04-21. 6-phase plan, locked decisions, safety guardrails,
          phase-summary template. THIS IS THE SINGLE SOURCE OF TRUTH FOR SCOPE.
2.  AlgoTrading_App_Features_and_AgentPrompt.md
        → Full long-term product vision (15 modules, 100+ features). The target
          end-state. Do NOT implement anything from this file unless it is
          explicitly listed in the current phase's features in MASTER_PLAN.md.
3.  docs/phases/PHASE_0_KICKOFF_PROMPT.md
        → The detailed working protocol for Phase 0. Contains the questionnaire
          format, TDD discipline rules, and the step-A-through-F procedure.
4.  backend/api/routes.py         → 16 FastAPI endpoints (do NOT break these)
5.  backend/main.py               → App factory, CORS config
6.  backend/data/market_data.py   → OHLCV fetching (yfinance + NSE fallback)
7.  backend/data/options_chain.py → NSE option chain scraper + synthetic fallback
8.  backend/indicators/engine.py  → RSI, MACD, SuperTrend, BB, PCR, confluence
9.  backend/ai/signal_engine.py   → Rule-based direction + entry/SL/target
10. backend/ai/budget_optimizer.py → Strike selection + lot sizing
11. backend/paper_trading/simulator.py → SQLite paper trade tracker
12. frontend/src/App.jsx          → Root React component
13. frontend/src/store/index.js   → Zustand state (all API calls live here)
14. frontend/src/lib/chartIndicators.js → Client-side technical analysis (927 lines)
15. backend/requirements.txt      → Python deps
16. frontend/package.json         → Node deps + build scripts

======================================================================
COMPLETE FILE STRUCTURE
======================================================================
nifty-options-bot/
├── .github/workflows/ci.yml        ← GitHub Actions: frontend build + backend import check
├── .gitignore                      ← Ignores .env, __pycache__, node_modules, *.db
├── AlgoTrading_App_Features_and_AgentPrompt.md  ← Long-term vision (read-only ref)
├── README.md                       ← Quick start, API table, phase roadmap
├── requirements.txt                ← Root-level reqs for Vercel Python runtime
├── vercel.json                     ← Vercel deploy config (FE static + Python BE)
├── api/
│   └── index.py                    ← Vercel serverless handler (imports backend routes)
├── backend/
│   ├── __init__.py
│   ├── main.py                     ← FastAPI app, CORS, route include
│   ├── requirements.txt            ← Full backend deps (uvicorn, anthropic, etc.)
│   ├── .env.example                ← Template: ANTHROPIC_API_KEY, KITE_API_KEY
│   ├── .env                        ← NEVER commit; holds real ANTHROPIC_API_KEY
│   ├── paper_trades.db             ← SQLite paper trading DB (gitignored)
│   ├── ai/
│   │   ├── signal_engine.py        ← Rule-based BUY_CE / BUY_PE / AVOID signal
│   │   └── budget_optimizer.py     ← Strike + lot sizing given budget
│   ├── api/
│   │   └── routes.py               ← All 16 FastAPI endpoints
│   ├── data/
│   │   ├── market_data.py          ← OHLCV via yfinance + direct Yahoo API fallback
│   │   └── options_chain.py        ← NSE option chain scraper + synthetic fallback
│   ├── indicators/
│   │   └── engine.py               ← RSI(14), MACD(12,26,9), SuperTrend(7,3),
│   │                                  Bollinger(20,2), PCR, volume, confluence score
│   └── paper_trading/
│       └── simulator.py            ← SQLite CRUD: enter/exit trade, stats, history
├── docs/
│   └── phases/
│       ├── MASTER_PLAN.md          ← THE PLAN (frozen 2026-04-21)
│       └── PHASE_0_KICKOFF_PROMPT.md ← Phase 0 detailed working protocol
└── frontend/
    ├── index.html
    ├── package.json                ← React 18, Zustand, lightweight-charts, Vite, Tailwind
    ├── vite.config.js              ← Port 5173, proxy /api → localhost:8000
    ├── tailwind.config.js          ← Custom terminal color palette
    ├── postcss.config.js           ← ESM export (requires "type":"module" in package.json)
    ├── dist/                       ← Build output (gitignored except index.html)
    └── src/
        ├── main.jsx                ← React entry point
        ├── App.jsx                 ← Root component, auto-refresh, layout grid
        ├── index.css               ← Tailwind base + marquee + glow utilities
        ├── store/
        │   └── index.js            ← Zustand store: ticker, signal, optimize, trades
        ├── lib/
        │   ├── chartIndicators.js  ← 927-line client-side indicator engine (EMA, RSI,
        │   │                          MACD, SuperTrend, HA, S/R, pivots, trade lifecycle)
        │   ├── yahooFetch.js       ← Dual-source OHLCV fetch (backend proxy → direct YF)
        │   └── newsService.js      ← RSS news fetch + keyword sentiment analysis
        └── components/
            ├── LiveChart.jsx       ← TradingView-style chart (candlestick, volume,
            │                          RSI sub-chart, MACD sub-chart, EMA, SuperTrend,
            │                          S/R, pivots, trade zone, fullscreen, intervals)
            ├── TickerBar.jsx       ← Scrolling index ticker (NIFTY, SENSEX, etc.)
            ├── MarketStatusBar.jsx ← Market open/closed + expiry countdown
            ├── TickerSelector.jsx  ← NIFTY / SENSEX selector + refresh button
            ├── SignalCard.jsx      ← AI signal display (direction, confidence, levels)
            ├── IndicatorGrid.jsx   ← Mini cards: RSI, MACD, ST, BB, PCR, confluence
            ├── BudgetOptimizer.jsx ← Strike + lot sizing given capital input
            ├── OptionChart.jsx     ← Option premium chart (Yahoo + NSE fallback)
            ├── MarketNews.jsx      ← RSS news feed + sentiment mood meter
            ├── TradeConfirmModal.jsx ← Paper trade confirmation dialog
            └── TradeHistory.jsx    ← Paper trade log + stats + exit action

======================================================================
CURRENT GIT STATE (as of 2026-04-26)
======================================================================
Branch: main
Uncommitted working-tree changes (NOT yet committed):
  M  backend/api/routes.py          (+20 lines — minor route additions)
  M  backend/data/market_data.py    (+107 lines — enhanced NSE/Yahoo fetch logic)
  M  docs/phases/MASTER_PLAN.md     (+4 lines — minor update)
  D  frontend/dist/assets/index-ShMRGirX.js  (old build artifact deleted)
  M  frontend/dist/index.html       (rebuilt)
  M  frontend/src/App.jsx           (+7 lines)
  M  frontend/src/components/LiveChart.jsx   (+24 lines)
  ?? AlgoTrading_App_Features_and_AgentPrompt.md  (untracked new file)
  ?? frontend/dist/assets/index-DDsUOeD9.js       (untracked new build artifact)

IMPORTANT: These changes exist only in the working tree — they have NOT been committed.
Before starting Phase 0 work, ask the user whether to commit these changes first
or leave them unstaged. Do NOT discard them.

Last 5 commits:
  4315738  Add AI tradebot phase plan and fix CI postcss build
  b440838  Add dynamic trade lifecycle, Heikin Ashi filter, and 1-day default view
  f0eae85  Fix volume bars, budget optimizer, market news, and Yahoo Finance fallback
  844d2a3  Fix volume bar compression, increase Buy/Sell marker size
  4a3ef63  Fix volume bar visibility and add RSI overbought/oversold zone shading

======================================================================
TECH STACK (current, as-shipped)
======================================================================
BACKEND
  Runtime:     Python 3.11
  Framework:   FastAPI 0.111.0 + uvicorn 0.30.1
  Data:        yfinance 0.2.40, httpx 0.27.0, pandas, numpy<2.0
  AI/LLM:      anthropic 0.28.0 (Anthropic API key in backend/.env)
  DB:          SQLite (aiosqlite 0.20.0) — paper trading only
  Scheduler:   apscheduler 3.10.4
  Config:      python-dotenv 1.0.1
  Start:       cd backend && uvicorn main:app --reload --port 8000

FRONTEND
  Framework:   React 18.3.1
  State:       Zustand 4.5.4
  Build:       Vite 5.3.4
  Styling:     Tailwind CSS 3.4.6 + PostCSS (ESM — requires "type":"module")
  Charts:      lightweight-charts 4.2.3 (TradingView library)
  HTTP:        axios 1.7.2
  Start:       cd frontend && npm run dev   (port 5173)

DEPLOYMENT
  Frontend:    Vercel static build (vercel.json)
  Backend:     Vercel Python serverless (api/index.py)
  CI:          GitHub Actions (.github/workflows/ci.yml)
               Job 1: npm ci && npm run build (Node 18)
               Job 2: pip install -r requirements.txt && python import check (Python 3.11)

API PROXY:     Vite dev server proxies /api → http://localhost:8000
               Vercel routes /api/* → api/index.py

======================================================================
BACKEND API ENDPOINTS (all currently working — do NOT break)
======================================================================
GET  /api/health                         → {"status":"ok"}
GET  /api/chart/{ticker}?interval=5m    → OHLCV via yfinance
GET  /api/nse-chart/{ticker}            → Real-time NSE intraday candles
GET  /api/yf-proxy                      → CORS proxy to Yahoo Finance
GET  /api/signal/{ticker}               → Rule-based signal (direction, confidence, levels)
POST /api/compute-signal                → Client sends OHLCV → server returns signal
POST /api/optimize                      → Budget optimizer (strike + lots)
POST /api/compute-optimize              → Client sends OHLCV → server returns optimization
GET  /api/market-status                 → NSE open/closed, IST time, next expiry
GET  /api/news                          → RSS market news (MoneyControl, ET, LiveMint)
POST /api/paper-trade/enter             → Log paper trade entry
POST /api/paper-trade/exit              → Close paper trade with P&L
GET  /api/paper-trade/history           → Last 100 trades
GET  /api/paper-trade/stats             → Win rate, total P&L, open count

======================================================================
LOCKED DECISIONS — DO NOT RE-ASK THESE, DO NOT REVERSE THEM
======================================================================
1. REAL MONEY: Deferred. Paper/prototype FIRST. All phases build real-money
   guardrails (flags default OFF, paper-vs-live toggle, daily loss cap, audit log),
   but actual live-broker activation against a real account is a MANUAL USER STEP
   taken only after Phases 0–5 are validated in sandbox/paper mode.
   Phase 4 ships SANDBOX only. Real-money flip is NOT part of any phase exit gate.

2. USER MODEL: SOLO. No auth, no `users` table, no JWT, no OTP, no OAuth.
   Single-tenant schema throughout. Can add auth later if user reverses this.

3. FIRST BROKER (Phase 4): Zerodha Kite Connect. Other brokers come later as
   adapter plugins. Do not wire Angel One / Upstox / Fyers in Phase 4.

4. DEPLOYMENT: Local dev first. Vercel + Render/Railway later. Do NOT touch
   vercel.json or CI config until the phase explicitly calls for it.

5. ML APPROACH (Phase 2): Classical ML first — XGBoost + regime classifier.
   Deep learning (LSTM, Transformers) is deferred. Do not propose DL in Phase 2.

6. INSTRUMENTS (Phase 1 backtest): Nifty 50 + Bank Nifty options only.
   Matches current UI. Do not expand to individual equities in Phases 0–2.

7. DEADLINE: None. Quality and TDD compliance over speed.

======================================================================
SAFETY GUARDRAILS — APPLY TO EVERY PHASE, NO EXCEPTIONS
======================================================================
1. ADDITIVE ONLY. Existing routes, UI, and behavior must keep working.
   New code goes in new modules. Never remove or rename a working endpoint.

2. FEATURE FLAGS DEFAULT OFF. ENABLE_ML_SIGNAL, ENABLE_LIVE_BROKER,
   ENABLE_AUTO_EXECUTION must default to false. The existing rule engine
   remains the source of truth until a flag is explicitly flipped by the user.

3. DB MIGRATIONS ARE ADDITIVE. New tables only in the phase they're introduced.
   Never drop or rename existing tables. Every migration must be reversible.

4. NO DESTRUCTIVE REFACTORS. If a module needs a rewrite, fork it into v2/
   and swap via config. Do not overwrite working code in-place.

5. EVERY PHASE ENDS WITH GREEN TESTS + WRITTEN SUMMARY. docs/phases/PHASE_{N}_SUMMARY.md
   must be fully populated using the template in MASTER_PLAN.md before declaring done.

6. SECRETS NEVER IN REPO. Every new env var goes in backend/.env.example
   with a placeholder. Never read or log actual key values.

======================================================================
HARD RULES — NON-NEGOTIABLE
======================================================================
- DO NOT delete, rename, or modify these files unless the phase explicitly requires it:
    backend/ai/signal_engine.py
    backend/indicators/engine.py
    Any frontend chart component
    Any existing working API endpoint

- DO NOT mock Postgres in integration tests. Use testcontainers or a
  disposable Docker postgres container. Unit tests may use sqlite-memory
  ONLY when the code under test is truly database-agnostic.

- DO NOT use --no-verify, --no-gpg-sign, or any git hook bypass.

- DO NOT weaken a TDD criterion silently. If one cannot be met, stop and
  escalate to the user with a concrete reason.

- DO NOT modify MASTER_PLAN.md without proposing the change to the user
  via questionnaire and getting explicit approval.

- Every database migration must have a working downgrade() function.

- Conventional commits format: feat(scope): ..., fix(scope): ..., test(scope): ..., etc.

======================================================================
THE 6-PHASE PLAN (summary — full detail in MASTER_PLAN.md)
======================================================================

PHASE 0 — Foundation Hardening (1–2 days) ← CURRENT PHASE, NOT YET STARTED
  Goal: Lay infrastructure rails. Zero new product features.
  Features:
  0.1 PostgreSQL + Alembic migrations. New tables (alongside existing SQLite):
      ohlcv_cache, signals, trades (Postgres version), backtest_runs, audit_log.
      Existing SQLite paper-trading flow keeps working unchanged.
      TDD: pytest migration up→insert→down; existing paper-trade smoke test passes.
  0.2 pytest (backend + pytest-asyncio) + vitest (frontend); coverage ≥ 60%
      on touched files. At least 3 example tests each side.
  0.3 .env + .env.example + pydantic-settings config loader.
      Required vars: DATABASE_URL, LOG_LEVEL, ENABLE_ML_SIGNAL (default false),
      ENABLE_LIVE_BROKER (default false), ENABLE_AUTO_EXECUTION (default false).
      Missing required var → startup raises with clear message naming the var.
  0.4 Verify CI postcss ESM fix (commit 4315738 added "type":"module" to
      frontend/package.json). Confirm GitHub Actions is green on main.
  0.5 Structured JSON logging + request-id propagation (FastAPI middleware).
      3 sequential requests → all log lines share same request_id.
  0.6 Feature-flag module at backend/config/feature_flags.py sourced from env.
      Single import everywhere: `from backend.config import feature_flags`.
      Integration test: flip flag → code path changes.
  Deliverables: docs/phases/PHASE_0_SUMMARY.md + docs/phases/PHASE_1_KICKOFF_PROMPT.md
  Exit gate: All 6 TDD criteria pass. User sign-off: "Phase 0 complete."

PHASE 1 — Backtesting Engine (3–5 days)
  Goal: Validate any strategy against history. Prerequisite for all ML work.
  Features (from MASTER_PLAN.md):
  1.1 Historical OHLCV store (Postgres, partitioned by year) for Nifty + BankNifty,
      1m/5m/15m/1d intervals. Range query < 200ms, idempotent loader.
  1.2 Vectorized backtester (pandas): BacktestRequest(strategy, start, end, capital)
      → BacktestResult. Replay rule-based engine on 2024 data, matches golden fixture.
  1.3 Metrics: Win%, Net P&L, Max Drawdown, Sharpe, Profit Factor, Expectancy.
  1.4 POST /api/backtest + GET /api/backtest/{id} endpoints.
  1.5 Frontend "Backtest" tab: date range, capital, equity curve (Recharts), trade log.
  1.6 Benchmark comparison vs. Nifty buy-and-hold.
  Exit gate: Backtester reproduces current rule-engine behavior on 2024 data exactly.

PHASE 2 — AI/ML Signal Layer (5–7 days)
  Goal: Replace/augment rule-based signals with trained models.
  Features (from MASTER_PLAN.md):
  2.1 Feature pipeline (sklearn.Pipeline): OHLCV + indicators → feature vector.
      No look-ahead leakage. Same input → same vector (hash-verified).
  2.2 Market regime classifier (HMM or KMeans): trending / ranging / volatile.
      Labels stable ≥ 80% week-over-week on 2024 held-out set.
  2.3 Direction model (XGBoost binary: up/down next N bars).
      Out-of-sample AUC ≥ 0.55 on 2024 Q4 held-out (random baseline 0.50).
  2.4 Confidence calibration (CalibratedClassifierCV). Brier score ≤ 0.24.
  2.5 Model registry (models/v{N}/) + version in DB + rollback via config flag.
  2.6 Shadow mode: ML runs alongside rule engine; both logged, only rule acts.
  2.7 ENABLE_ML_SIGNAL flag flips engine. Flag OFF = zero regression in existing signal.
  Exit gate: ML beats random on AUC; 1-week shadow run; rule engine unaffected when OFF.

PHASE 3 — Risk Management Engine (3–4 days) — REQUIRED BEFORE PHASE 4
  Goal: Make the bot safe enough for real money. Not optional.
  Features (from MASTER_PLAN.md):
  3.1 Per-trade SL/TP (₹, %, points) + trailing SL.
  3.2 Daily SL / Daily TP auto-cutoff across all deployments.
  3.3 Position sizing: fixed-qty / fixed-₹ / % of portfolio / Kelly-fraction.
  3.4 Kill switch: POST /api/kill-switch → all open orders cancelled, all
      deployments halted within 1 second; subsequent signals ignored.
  3.5 Max open positions cap per strategy and globally.
  Exit gate: All 5 TDD criteria pass; exercised in paper mode ≥ 3 days without anomalies.

PHASE 4 — Live Broker Integration (Zerodha) (4–6 days) — SANDBOX ONLY
  Goal: Place real orders via Zerodha Kite Connect. ENABLE_LIVE_BROKER=false by default.
  Real-money activation is NOT part of this phase's exit gate.
  Features (from MASTER_PLAN.md):
  4.1 Broker adapter interface: place_order, modify_order, cancel_order,
      get_positions, get_orders. Contract tests against Kite sandbox.
  4.2 Zerodha Kite Connect adapter implementing the interface.
  4.3 Paper-vs-live toggle at deployment level (default paper).
      ENABLE_LIVE_BROKER=false globally blocks live even if toggle is on.
  4.4 Order state machine: PENDING → PLACED → FILLED / REJECTED / CANCELLED.
  4.5 Encrypted API-key storage (Fernet + per-install salt).
  4.6 Idempotent order placement (client-order-id). Duplicate webhook → 1 order.
  4.7 Audit log: every order attempt + every flag flip, immutable Postgres table.
  Exit gate: Sandbox orders work end-to-end. Commit 4315738 or descendant is green in CI.

PHASE 5 — Real-time & Notifications (2–3 days)
  5.1 WebSocket endpoint for live P&L + position updates.
  5.2 Telegram bot integration (trade entry/exit/SL hit/daily cutoff alerts).
  5.3 Email alerts (daily summary + critical events).
  5.4 Alert de-dup: same signal within 60s → 1 alert.
  Exit gate: Live P&L streams to frontend; Telegram/email fire reliably; no duplicate spam.

PHASE 6 — Analytics, Scanner, Admin (3–4 days)
  6.1 Portfolio analytics: capital allocation, cumulative returns, drawdown chart.
  6.2 Market scanner: top gainers/losers, volume spike, breakout on 500 tickers.
  6.3 Admin view (solo mode): deployments list, audit log viewer, flag toggle UI.

======================================================================
PHASE-SUMMARY DOCUMENT TEMPLATE (mandatory before declaring any phase done)
======================================================================
Every phase ends with this file written at docs/phases/PHASE_{N}_SUMMARY.md:

# Phase {N} Summary — {Phase Name}
**Status:** ✅ Complete | ⏳ In progress | ⛔ Blocked
**Duration:** {start date} → {end date}

## Scope delivered
- [x] Feature {N.1} — description (commit: abc123)
- [ ] Feature {N.X} — DEFERRED to Phase {M} (reason: ...)

## TDD criteria results
| # | Criterion | Status | Evidence |
|---|---|---|---|
| N.1 | ... | ✅ pass | tests/test_xxx.py::test_yyy |

## Architecture decisions
- ADR-00X: {title} — {chosen option, 1-line rationale}

## Known risks / debt opened
- {risk} — mitigation: {plan}

## Handoff to Phase {N+1}
### Context the next agent must know
### Open questions deferred
### Files/paths the next phase will touch
### "Don't do this" list

======================================================================
WORKING PROTOCOL FOR PHASE 0 (from PHASE_0_KICKOFF_PROMPT.md)
======================================================================
Follow steps A through F in order. Never skip or reorder.

STEP A — ORIENT (no code)
  Read all 16 authoritative sources. Post a one-page "Understanding & Gaps" note:
  - What Phase 0 means in context of the existing code
  - Any ambiguities found
  - Proposed file layout (paths only, no code)
  Wait for user acknowledgement before proceeding.

STEP B — QUESTIONNAIRE-DRIVEN CLARIFICATION
  For every decision where confidence < 95%, ask ONE question at a time:
  - Format: <QUESTION id="Q1" type="radio"> block (see PHASE_0_KICKOFF_PROMPT.md)
  - Always include DEFAULT and WHY-ASKING fields
  - Ask the most blocking question first
  - If the answer is findable in the repo, find it — do NOT ask
  - Never batch unrelated questions in one prompt

STEP C — CONFIDENCE GATE
  When confidence reaches ≥ 95%, state: "Confidence: 95%+. Proceeding to plan."
  Post list of files to create/modify + test-first order.
  Wait for user "go".

STEP D — TDD IMPLEMENTATION (one feature at a time, 0.1 → 0.6)
  For each feature:
  1. Write the failing test matching the TDD criterion in MASTER_PLAN.md
  2. Show failing test output; ask "Approve this test? (Yes / Adjust / Skip)"
  3. Implement minimal code to pass
  4. Run test suite; show results
  5. Mark feature row in PHASE_0_SUMMARY.md as ✅ IMMEDIATELY (never batch)
  6. Commit (conventional commits format)
  Never implement more than one feature ahead of the summary doc update.

STEP E — ANSWER QUESTIONS INLINE
  Answer any user questions with file citations (path:line) immediately.

STEP F — CLOSE THE PHASE CHECKLIST
  [ ] All 6 TDD criteria pass
  [ ] Backend pytest green + coverage report generated
  [ ] Frontend vitest green
  [ ] GitHub Actions CI green on a test push
  [ ] docs/phases/PHASE_0_SUMMARY.md fully populated
  [ ] docs/phases/PHASE_1_KICKOFF_PROMPT.md generated with handoff context
  [ ] Existing paper trading flow: manual smoke test documented
  Then ask: "Phase 0 complete. Approve merge? (Yes / Request changes)"

======================================================================
KEY DOMAIN KNOWLEDGE
======================================================================
Market hours: IST 9:15 AM – 3:30 PM (Mon–Fri). IST = UTC+5:30.
Nifty 50 options expire every Thursday. Bank Nifty every Wednesday.
Sensex options expire every Friday.
Lot sizes: NIFTY=25, BANKNIFTY=15, SENSEX=20.
Yahoo Finance symbols: NIFTY→^NSEI, SENSEX→^BSESN, BANKNIFTY→^NSEBANK.
NSE API blocks non-Indian IPs — all NSE calls have a synthetic fallback.
Option chain cache: 90 seconds. OHLCV cache: 10 seconds.
P&L for CE: (exit - entry) × lots × lot_size
P&L for PE: (entry - exit) × lots × lot_size  ← note: inverted

======================================================================
ENVIRONMENT VARIABLES (current .env.example structure)
======================================================================
# backend/.env.example
ANTHROPIC_API_KEY=your_anthropic_api_key_here
APP_ENV=development
# Phase 3/4 only — leave blank until then:
KITE_API_KEY=
KITE_ACCESS_TOKEN=

# To be added in Phase 0:
DATABASE_URL=postgresql://user:pass@localhost:5432/nifty_bot
LOG_LEVEL=INFO
ENABLE_ML_SIGNAL=false
ENABLE_LIVE_BROKER=false
ENABLE_AUTO_EXECUTION=false

======================================================================
TERMINAL COLOR PALETTE (Tailwind — do not change)
======================================================================
terminal-bg:      #0f172a   (page background)
terminal-surface: #1e293b   (card backgrounds)
terminal-border:  #334155   (dividers)
terminal-muted:   #475569   (secondary text)
terminal-dim:     #94a3b8   (tertiary text)
terminal-text:    #f1f5f9   (primary text)
terminal-green:   #22c55e   (bullish/profit)
terminal-red:     #ef4444   (bearish/loss)
terminal-amber:   #f59e0b   (caution/warning)
terminal-blue:    #3b82f6   (info/neutral)

======================================================================
LONG-TERM VISION (reference only — do NOT implement ahead of phase)
======================================================================
AlgoTrading_App_Features_and_AgentPrompt.md describes the full target:
15 modules including no-code strategy builder, multi-broker support,
ML regime detection, market scanner, portfolio analytics, admin panel,
Telegram/email/push notifications, and tax reporting.
This vision is the "north star." Only build what MASTER_PLAN.md explicitly
assigns to the current phase.

======================================================================
START INSTRUCTION
======================================================================
Begin with STEP A. Read all 16 authoritative sources listed above.
Post your "Understanding & Gaps" note (one paragraph max per topic).
Wait for the user's acknowledgement before asking any questions.
Do not write code until Step D.
```

---

## QUICK-START COMMANDS (for human reference)

```bash
# Start backend
cd backend
cp .env.example .env   # fill in ANTHROPIC_API_KEY
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Start frontend (new terminal)
cd frontend
npm install
npm run dev            # http://localhost:5173

# Run CI check locally
cd frontend && npm run build
cd ../backend && python -c "import indicators.engine, ai.signal_engine, ai.budget_optimizer; print('OK')"
```

---

## MEMORY NOTES (Claude Code persistent memory)

From `~/.claude/projects/.../memory/`:

- **project_ai_tradebot_plan.md**: Plan locked 2026-04-21. Real-money deferred by
  user decision 2026-04-25. All phases build real-money guardrails but activation
  is manual post Phases 0–5 validation. Solo user model.

- **project_ci_fix.md**: CI postcss ESM fix is in commit 4315738 (`"type":"module"`
  added to frontend/package.json). Still needs a confirmed green CI run to close
  out Phase 0 Feature 0.4.
