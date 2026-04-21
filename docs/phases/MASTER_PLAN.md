# AI Tradebot Upgrade — Master Plan

**Frozen:** 2026-04-21
**Goal:** Evolve the existing Nifty options bot into a full AI-driven trading platform without breaking what currently works.

---

## Decisions locked in (from user)

| Decision | Value | Consequence |
|---|---|---|
| Real-money usage | **Unsure → treat as YES for safety** | All phases use real-money guardrails: paper-vs-live toggle default-off, mandatory sandbox tests before live broker calls, daily loss cap hardcoded, two-confirmation kill switch, audit log for every order. |
| User model | **Solo user** | No auth, no `users` table in Phase 0. Skip JWT/OTP/OAuth. Single-tenant DB schema. Can be upgraded later via migration. |
| First broker (Phase 4) | Zerodha Kite Connect | Other brokers (Angel One, Upstox, Fyers, 5paisa) implemented as adapter plugins in a future phase. |
| Deployment target | Local dev first, Vercel (FE) + Render/Railway (BE) later | No infra migration until code is ready. |
| ML approach (Phase 2) | Classical ML first (XGBoost + regime classifier) | Deep learning deferred. |
| Instruments for Phase 1 backtest | Nifty 50 + Bank Nifty options only | Matches current UI support. |
| Deadline | None; quality over speed | Each phase ships when its TDD criteria are green. |

---

## Safety guardrails (apply to every phase)

1. **Additive only.** Existing routes, UI, and behavior keep working. New code lives in new modules.
2. **Feature flags default OFF.** `ENABLE_ML_SIGNAL`, `ENABLE_LIVE_BROKER`, `ENABLE_AUTO_EXECUTION` — rule engine remains the source of truth until explicitly flipped.
3. **DB migrations are additive.** New tables only; never drop or rename existing tables in the same phase they're introduced.
4. **No destructive refactors.** If a module needs a rewrite, fork it into `v2/` and swap via config when confident.
5. **Every phase ends with green tests + a written summary doc** (`docs/phases/PHASE_{N}_SUMMARY.md`) before moving on.
6. **Secrets never in repo.** Every new env var goes in `.env.example` with a placeholder value.

---

## Current-state baseline (what exists today)

- **Backend:** FastAPI, 16 routes (see [backend/api/routes.py](../../backend/api/routes.py)), Yahoo Finance + NSE dual data source, rule-based signal engine, in-memory SQLite paper trading
- **Frontend:** React 18 + Vite + Zustand + Tailwind, 12 components, TradingView-style live chart
- **Indicators:** RSI, MACD, Supertrend, Bollinger, EMA, ATR — [backend/indicators/engine.py](../../backend/indicators/engine.py)
- **AI today:** rule-based confluence scoring in [backend/ai/signal_engine.py](../../backend/ai/signal_engine.py) (no ML model)
- **Missing for "AI tradebot":** persistent DB, backtester, ML pipeline, risk engine, broker integration, real-time WS, notifications, regime detection

---

# The 6 phases

Each phase is self-contained and shippable. Phase order is deliberate — you cannot validate an ML model without a backtester, and you cannot safely wire a broker without a risk engine.

---

## Phase 0 — Foundation Hardening
**Duration:** 1–2 days
**Goal:** Lay rails so later phases don't get stuck. No product features added.

### Features
| # | Feature | TDD Test Criteria |
|---|---|---|
| 0.1 | PostgreSQL + Alembic migrations; new `trades`, `signals`, `backtest_runs`, `ohlcv_cache` tables added **alongside** existing SQLite paper trading | `pytest`: migration up → insert row → migration down → row gone. Existing SQLite paper-trade flow still works unchanged. |
| 0.2 | `pytest` backend (+ `pytest-asyncio`) and `vitest` frontend wired; coverage ≥ 60% on touched files | CI runs both. Coverage report artifact uploaded. Build fails if coverage on touched files drops. |
| 0.3 | `.env` + `.env.example` + `pydantic-settings` config loader | Unit test: missing required env var → startup error with clear message naming the var. |
| 0.4 | Fix CI postcss ESM (already done as prep commit); confirm GitHub Actions green | `npm run build` passes in CI. |
| 0.5 | Structured JSON logging + request-id propagation | Hit 3 endpoints in sequence → all log lines share same `request_id`. |
| 0.6 | Feature-flag module (`settings.feature_flags.ENABLE_X`) with defaults | Toggling any flag off → corresponding code path not entered (asserted via integration test). |

### Deliverables
- `docs/phases/PHASE_0_SUMMARY.md` filled in
- `docs/phases/PHASE_1_KICKOFF_PROMPT.md` generated with handoff context
- DB connection string, feature-flag defaults documented

### Exit gate
All 6 TDD criteria pass. User sign-off: "Phase 0 complete."

---

## Phase 1 — Backtesting Engine
**Duration:** 3–5 days
**Goal:** Make it possible to validate any strategy against history. Prerequisite for all ML work.

### Features
| # | Feature | TDD Test Criteria |
|---|---|---|
| 1.1 | Historical OHLCV store (Postgres table, partitioned by year) for Nifty + BankNifty, 1m/5m/15m/1d intervals | Given 2 yrs of 5-min candles → range query < 200 ms. Idempotent loader (re-run doesn't duplicate rows). |
| 1.2 | Vectorized backtester (pandas): `BacktestRequest(strategy, start, end, capital) → BacktestResult` | Replay current rule-based signal engine against 2024 data → trade count matches golden fixture exactly. |
| 1.3 | Metrics module: Win %, Net P&L, Max Drawdown, Sharpe, Profit Factor, Expectancy | Unit: known P&L series → Sharpe matches `scipy` reference value to 4 decimals. |
| 1.4 | `POST /api/backtest` + `GET /api/backtest/{id}` endpoints | Integration test: POST run → poll GET → status=complete, result JSON shape locked. |
| 1.5 | Frontend "Backtest" tab: date range picker, capital input, run button, equity curve (Recharts), trade log table | Playwright-lite/vitest component test: submit form → curve renders within 2 s on mocked result. |
| 1.6 | Benchmark comparison (strategy vs. Nifty buy-and-hold) on same date range | Snapshot: same seed → identical curve JSON. |

### Exit gate
Backtester reproduces current rule-engine behavior on 2024 data exactly, and produces a performance report.

---

## Phase 2 — AI/ML Signal Layer
**Duration:** 5–7 days
**Goal:** Replace (or augment) rule-based signals with trained models. This is the "AI" milestone.

### Features
| # | Feature | TDD Test Criteria |
|---|---|---|
| 2.1 | Feature pipeline (`sklearn.Pipeline`): OHLCV + indicators → feature vector | Same input → same vector, hash-verified. No look-ahead leakage (test: future candle mutation doesn't change past feature). |
| 2.2 | **Market regime classifier** — HMM or KMeans on (volatility, returns, ADX) → {trending, ranging, volatile} | Labels stable ≥ 80% week-over-week on 2024 held-out set. |
| 2.3 | **Direction model** — XGBoost binary: up/down next N bars | Out-of-sample AUC ≥ 0.55 on 2024 Q4 held-out. (Random baseline 0.50.) |
| 2.4 | Confidence calibration via `CalibratedClassifierCV` | Brier score ≤ 0.24 on test; reliability diagram PNG committed to `docs/ml/`. |
| 2.5 | Model registry (`models/v{N}/`) + version in DB; rollback via config flag | Integration test: flip `ML_MODEL_VERSION=v1` → served model matches; flip back → served model reverts. |
| 2.6 | Shadow-mode: ML signal runs alongside rule engine; both logged, only rule acts | 1 week shadow → dashboard shows agreement rate, per-signal divergence trades surfaced. |
| 2.7 | `ENABLE_ML_SIGNAL` flag flips engine from rule → ML (still paper only) | With flag ON: `/api/signal/{ticker}` returns model output; with flag OFF: current rule output (no regression). |

### Exit gate
ML model beats random on held-out test AUC, runs in shadow for ≥ 1 week, rule engine still works when flag off.

---

## Phase 3 — Risk Management Engine
**Duration:** 3–4 days
**Goal:** Make the bot safe enough to trust with real money. **Required before Phase 4.**

### Features
| # | Feature | TDD Test Criteria |
|---|---|---|
| 3.1 | Per-trade SL/TP (₹, %, points) + trailing SL | Replay: entry → price up 2% → trail ratchets → exit at exact expected level. |
| 3.2 | Daily SL / Daily TP auto-cutoff across all deployments | Sim: 3 losing trades hit daily limit → 4th trade blocked with reason logged. |
| 3.3 | Position sizing: fixed-qty / fixed-₹ / % of portfolio / Kelly-fraction | Boundary: capital 1L, risk 2%, SL 5 pts → qty = 400 exactly. |
| 3.4 | Kill switch endpoint `POST /api/kill-switch` — cancels all open orders + halts all deployments | Integration: flip switch → all deployments `status=halted` within 1 s; subsequent signals ignored. |
| 3.5 | Max open positions cap per strategy and globally | Test: open N+1 position → rejection with clear error. |

### Exit gate
All 5 TDD criteria pass. Risk engine has been exercised in paper mode for ≥ 3 days without anomalies.

---

## Phase 4 — Live Broker Integration (Zerodha)
**Duration:** 4–6 days
**Goal:** Place real orders via Zerodha Kite Connect. **Default OFF behind feature flag.**

### Features
| # | Feature | TDD Test Criteria |
|---|---|---|
| 4.1 | Broker adapter interface: `place_order`, `modify_order`, `cancel_order`, `get_positions`, `get_orders` | Contract tests run against Kite sandbox; all 5 methods green. |
| 4.2 | Zerodha Kite Connect adapter implementing the interface | Sandbox integration test: place market order → receive ack → query order → state = COMPLETE. |
| 4.3 | Paper-vs-live toggle at deployment level (default paper) | Flipping toggle routes next signal to correct adapter (mock-asserted). Flag `ENABLE_LIVE_BROKER=false` globally blocks even if toggle is on. |
| 4.4 | Order state machine: `PENDING → PLACED → FILLED / REJECTED / CANCELLED`, persisted in Postgres | Reject-path test: broker returns reject → position not opened, error surfaced in UI, audit-logged. |
| 4.5 | Encrypted API-key storage (Fernet + per-install salt) | Round-trip: save key → retrieve → plaintext never appears on disk or in logs. |
| 4.6 | Idempotent order placement (client-order-id) | Duplicate webhook → single order in DB. |
| 4.7 | Audit log: every order attempt + every flag flip, immutable table | Query audit log after test run → every action present with timestamp + actor. |

### Exit gate
Sandbox orders work end-to-end. Flipping `ENABLE_LIVE_BROKER=true` in real account is a **manual step** gated by user confirmation, not part of this phase's completion.

---

## Phase 5 — Real-time & Notifications
**Duration:** 2–3 days

### Features
| # | Feature | TDD Test Criteria |
|---|---|---|
| 5.1 | WebSocket endpoint for live P&L + position updates | 3 clients connected → all receive tick within 500 ms of server event. |
| 5.2 | Telegram bot integration — alerts on entry / exit / SL hit / daily cutoff | Trigger entry → test Telegram channel receives message with correct fields. |
| 5.3 | Email alerts (daily summary + critical events) | Daily summary cron fires → email sent with P&L table. |
| 5.4 | Alert de-dup: same signal within 60 s → 1 alert | Fire same signal 3× in 30 s → exactly 1 alert delivered. |

### Exit gate
Live P&L streams to frontend, Telegram/email fire reliably, no duplicate spam.

---

## Phase 6 — Analytics, Scanner, Admin
**Duration:** 3–4 days

### Features
| # | Feature | TDD Test Criteria |
|---|---|---|
| 6.1 | Portfolio analytics page: capital allocation, cumulative returns, drawdown chart | Given seeded trades → curves match golden JSON snapshot. |
| 6.2 | Market scanner: top gainers/losers, volume spike, breakout on 500 tickers | Full scan on 5-min interval < 10 s. |
| 6.3 | Simple admin view (solo mode): deployments list, audit log viewer, flag toggle UI | Flag toggled in UI → reflected in backend within 1 s; audit entry created. |

### Exit gate
All analytics widgets render correctly from real trade data; scanner usable.

---

# Phase-summary document template

Each phase's implementation agent writes this file **before** declaring the phase complete:

```markdown
# Phase {N} Summary — {Phase Name}
**Status:** ✅ Complete | ⏳ In progress | ⛔ Blocked
**Duration:** {start date} → {end date}
**Completed by:** {agent session id / date}

## Scope delivered
- [x] Feature {N.1} — {description} (commit: abc123)
- [x] Feature {N.2} — ...
- [ ] Feature {N.3} — DEFERRED to Phase {M} (reason: ...)

## TDD criteria results
| # | Criterion | Status | Evidence |
|---|---|---|---|
| N.1 | ... | ✅ pass | tests/test_xxx.py::test_yyy |
| N.2 | ... | ✅ pass | link to CI run |

## Architecture decisions
- **ADR-00X:** {title} — {chosen option, 1-line rationale}

## Known risks / debt opened
- {risk} — mitigation: {plan}

## Handoff to Phase {N+1}
### Context the next agent must know
- {state of DB schema, model versions, feature-flag values}

### Open questions deferred
- {Q: ...} — proposed default: {...}

### Files/paths the next phase will touch
- {predicted hot spots}

### "Don't do this" list
- {dead ends discovered; saves next agent time}
```

---

# Collaborative agent prompt (paste-ready template, per phase)

Each phase's kickoff prompt (`docs/phases/PHASE_{N}_KICKOFF_PROMPT.md`) is derived from this template. Phase 0's is already generated.

The prompt enforces:
- Read authoritative sources first
- Ask ONE questionnaire-style question at a time for every <95% confidence decision
- TDD discipline — failing test first, user approves test, then implement
- Phase-summary doc updated **as work progresses**, not at the end
- Generate next phase's kickoff prompt before declaring done

See `PHASE_0_KICKOFF_PROMPT.md` for the concrete instance.

---

**End of Master Plan.**
