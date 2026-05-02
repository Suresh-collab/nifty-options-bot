# Phase 3 Summary — Risk Management Engine
**Status:** ✅ Complete
**Duration:** 2026-05-02
**Completed by:** Claude Sonnet 4.6 agent session

---

## Scope delivered

- [x] 3.1 Per-trade SL/TP + trailing stop — `backend/risk/engine.py`: `check_sl_tp()`, `initial_trail_state()`, `trailing_sl_exit_price()`; BUY_CE and BUY_PE logic; trail ratchets on new highs/lows
- [x] 3.2 Daily loss/profit cutoff — `check_daily_cutoff()` in risk engine; wired into `POST /api/paper-trade/enter` (HTTP 403 with reason when limit hit)
- [x] 3.3 Position sizing — `size_position_risk_pct()`, `size_position_fixed_inr()`, `size_position_kelly()` in risk engine; TDD boundary: 1L capital, 2% risk, 5pt SL → qty=400 ✅
- [x] 3.4 Kill switch — `POST /api/kill-switch` sets `_kill_switch_active=True`, calls `halt_all_open()` on SQLite, writes audit log to Neon; `GET /api/kill-switch/status` reflects state; subsequent `paper-trade/enter` → 403
- [x] 3.5 Max open positions cap — `check_max_positions()` in risk engine; wired into `paper-trade/enter` gate; default cap = 5 (configurable via `MAX_OPEN_POSITIONS` env var)

---

## TDD criteria results

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 3.1 | Replay: entry → price up 2% → trail ratchets → exit at exact expected level | ✅ pass | `test_trailing_sl_ratchets_on_new_high`, `test_trailing_exit_price_formula` |
| 3.2 | 3 losing trades hit daily limit → 4th trade blocked with reason logged | ✅ pass | `test_paper_enter_blocked_by_daily_loss_limit` (HTTP 403 + "daily cutoff" in detail) |
| 3.3 | capital=1L, risk=2%, SL=5pts → qty=400 exactly | ✅ pass | `TestPositionSizing::test_risk_pct_tdd_boundary` |
| 3.4 | Kill switch → all open trades HALTED within response; subsequent signals ignored | ✅ pass | `test_kill_switch_halts_open_trades`, `test_kill_switch_blocks_subsequent_paper_enter` |
| 3.5 | Open N+1 position → rejection with clear error | ✅ pass | `test_paper_enter_blocked_when_positions_full` (HTTP 403 + "position cap" in detail) |

**Full test run: 91 passed, 1 skipped (DB migration), 0 failures.**

---

## Architecture decisions

- **ADR-013: Pure functions in risk/engine.py** — No DB or HTTP dependencies. All risk logic is stateless and testable without a running server. The routes layer reads simulator state and passes values in. Easy to unit-test boundary conditions exactly.
- **ADR-014: In-memory kill switch flag** — `_kill_switch_active` in routes.py resets on server restart (intentional — requires operator action to resume). For Phase 4+, this could be persisted to DB or a Redis key, but in-memory is sufficient for paper trading.
- **ADR-015: Risk gate inside paper_enter route** — Checks happen in this order: kill switch → daily cutoff → position cap → enter. First failing check returns 403 with a descriptive reason. Existing paper-trade history/stats/exit routes are unaffected.
- **ADR-016: halt_all_open marks status='HALTED'** — Distinct from 'CLOSED' so halted trades are visible in history and not counted in P&L stats (no exit_price set). This is additive — no schema changes required.

---

## New files created

```
backend/risk/__init__.py
backend/risk/engine.py              Pure risk functions (3.1–3.5)
tests/test_risk_engine.py           30 tests — all 5 TDD criteria (unit + API)
```

## Modified files

```
backend/config/settings.py          + paper_trading_capital, daily_loss_limit_pct,
                                      daily_profit_target_pct, max_open_positions
backend/paper_trading/simulator.py  + get_daily_pnl(), get_open_count(), halt_all_open()
backend/api/routes.py               + _kill_switch_active flag
                                    + risk gate in paper_enter (kill switch, daily cutoff, position cap)
                                    + POST /api/kill-switch
                                    + GET /api/kill-switch/status
backend/.env.example                (updated in Phase 2 completion; covers Phase 3 vars)
```

---

## Test counts

| Suite | Tests | Status |
|---|---|---|
| Backend pytest | 91 | All green (1 skipped = DB migration) |
| Frontend vitest | 11 | All green (unchanged) |

---

## Known risks / debt opened

- **Kill switch is not persistent** — Server restart re-enables trading. For Phase 4 (live broker), the kill switch state MUST be persisted (DB flag or env var). Treating this as acceptable for paper-only Phase 3.
- **No trailing SL monitor loop** — `check_sl_tp()` is a pure function; it doesn't poll prices. A real trailing stop needs a background task polling current prices against open trades. This is deferred to Phase 5 (WebSocket / real-time infrastructure). For now, the function is ready and tested; the polling harness comes later.
- **Daily cutoff resets on server restart** — `get_daily_pnl()` queries SQLite for today's closed trades, so it survives restarts correctly. ✅ No issue here.
- **`halt_all_open` sets no exit_price** — Halted trades show `pnl=0` in stats. Phase 4 should record the last known market price as a notional exit.

---

## Handoff to Phase 4

### Context the next agent must know
- Risk gate order in `paper_enter`: kill switch → daily cutoff → position cap → enter
- `_kill_switch_active` is module-level in `api/routes.py` — server restart clears it
- `get_daily_pnl()` uses `datetime.now().strftime("%Y-%m-%d")` — IST-naive (local server time). Phase 4 should use IST-aware datetime if server runs in UTC
- `halt_all_open()` uses status='HALTED'; `get_open_count()` only counts status='OPEN'
- Risk settings are in `Settings` and configurable via env: `PAPER_TRADING_CAPITAL`, `DAILY_LOSS_LIMIT_PCT`, `DAILY_PROFIT_TARGET_PCT`, `MAX_OPEN_POSITIONS`

### Files Phase 4 will touch
- NEW: `backend/broker/` — Zerodha Kite Connect adapter + interface
- NEW: `backend/models/orders.py` — order state machine (PENDING→PLACED→FILLED/REJECTED)
- `backend/api/routes.py` — broker order endpoints, paper-vs-live toggle
- `backend/paper_trading/simulator.py` — wire risk engine into exit flow (SL/TP auto-exit)

### "Don't do this" list
- Do NOT enable `ENABLE_LIVE_BROKER=true` until Phase 0–4 full paper validation is signed off
- Do NOT modify the kill switch to auto-reset — operator must restart server intentionally
- Do NOT remove the `status='HALTED'` distinction — it's needed for audit trail in Phase 6
