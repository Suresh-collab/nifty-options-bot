# Phase 5 Summary — Real-time & Notifications
**Status:** ✅ Complete
**Duration:** 2026-05-02
**Completed by:** Claude Sonnet 4.6 agent session

---

## Scope delivered

- [x] 5.1 WebSocket live P&L stream — `backend/api/ws.py`; `/ws/live` endpoint; `broadcast()` helper; background `_pnl_poller` task started via FastAPI lifespan; pushes paper-trade state every second to all connected clients; dead clients pruned automatically
- [x] 5.2 Telegram alerts — `backend/notifications/telegram.py`; `send_trade_alert()` fires on trade entry, exit, SL hit, daily cutoff, kill switch; required fields (ticker, direction, strike, price, optional P&L) always present; uses httpx (no extra library)
- [x] 5.3 Email alerts — `backend/notifications/email.py`; `send_daily_summary()` builds HTML P&L table and sends via aiosmtplib (STARTTLS); `send_critical_alert()` for kill switch / daily cutoff events
- [x] 5.4 Alert de-dup — `backend/notifications/dedup.py`; `AlertDedup` class with configurable TTL (default 60 s); module-level singleton shared by Telegram + email; same alert key within TTL → exactly 1 delivery

---

## TDD criteria results

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 5.1 | 3 clients connected → all receive tick within 500 ms | ✅ pass | `test_broadcast_reaches_all_three_clients`, `test_broadcast_within_500ms` |
| 5.2 | Trigger entry → Telegram message has ticker, direction, strike, price | ✅ pass | `test_send_trade_alert_contains_required_fields` |
| 5.3 | Daily summary cron → email sent with P&L table | ✅ pass | `test_send_daily_summary_calls_smtp` |
| 5.4 | Same signal 3× in 30 s → exactly 1 alert delivered | ✅ pass | `test_three_calls_within_ttl_exactly_one_delivered`, `test_telegram_dedup_suppresses_duplicates` |

**Full test run: 143 passed, 1 skipped (DB migration), 0 failures.**

---

## Architecture decisions

- **ADR-022: httpx for Telegram (no telegram-bot library)** — Telegram Bot API is a plain HTTPS POST. httpx is already in requirements; no extra dependency needed.
- **ADR-023: aiosmtplib for email** — Async SMTP keeps the event loop non-blocking. Falls back gracefully (returns False) when SMTP config is missing.
- **ADR-024: Module-level AlertDedup singleton** — Both telegram.py and email.py share the same dedup store via `notifications.dedup.should_send()`. This prevents the same event from being sent by both channels simultaneously within the TTL window.
- **ADR-025: Fire-and-forget for alerts in routes** — Trade alerts in `paper_enter` / `paper_exit` use `asyncio.ensure_future()` so notification failures never block or fail the trade response. All failures are logged as WARNING.
- **ADR-026: FastAPI lifespan for background poller** — P&L poller started in `@asynccontextmanager lifespan` in `main.py`, replacing the deprecated `@app.on_event("startup")` pattern. Task is cancelled cleanly on shutdown.
- **ADR-027: /ws/live outside /api prefix** — WebSocket at `/ws/live` (not `/api/ws/live`) to keep it separate from REST routes and allow different auth/proxy rules in Phase 6.

---

## New files created

```
backend/notifications/__init__.py
backend/notifications/dedup.py          AlertDedup class + module singleton (5.4)
backend/notifications/telegram.py       send_message(), send_trade_alert() (5.2)
backend/notifications/email.py          send_email(), send_daily_summary(), send_critical_alert() (5.3)
backend/api/ws.py                       WebSocket endpoint, broadcast(), _pnl_poller (5.1)
tests/test_phase5_notifications.py      24 tests — all 4 TDD criteria
```

## Modified files

```
backend/main.py            + lifespan context manager; include ws_router; start_pnl_poller()
backend/api/routes.py      + fire-and-forget trade_entry/exit Telegram alert + WS broadcast
                           + kill switch fires Telegram + email + WS broadcast
backend/config/settings.py + telegram_bot_token, telegram_chat_id, smtp_*, alert_email_to,
                             alert_dedup_ttl
backend/requirements.txt   + aiosmtplib>=3.0.0
backend/.env.example       + TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SMTP_*, ALERT_EMAIL_TO,
                             ALERT_DEDUP_TTL
```

---

## Test counts

| Suite | Tests | Status |
|---|---|---|
| Backend pytest | 143 | All green (1 skipped = DB migration) |
| Frontend vitest | 11 | All green (unchanged) |

---

## Known risks / debt opened

- **Poller resets on server restart** — `last_payload` in `_pnl_poller` is in-memory; first broadcast after restart always fires regardless of change. Acceptable.
- **No Telegram webhook for order updates from Kite** — Phase 4 noted this; add `POST /api/broker/webhook` + push via `broadcast()` in future.
- **Daily summary has no cron trigger** — `send_daily_summary()` is implemented and tested but no scheduler fires it at market close (3:30 PM IST). Wire to APScheduler or a cron in Phase 6.
- **WebSocket has no auth** — `/ws/live` is open. For solo-user deployment this is acceptable; add token query-param auth if exposed publicly.
- **`alert_dedup_ttl` from settings not wired to module singleton** — The module-level `_dedup` in `dedup.py` uses hard-coded `ttl_seconds=60`. Phase 6 should call `_dedup._ttl = get_settings().alert_dedup_ttl` at startup.

---

## Handoff to Phase 6

### Context the next agent must know
- `broadcast(data)` in `api/ws.py` is the single function to push to all WS clients — import and call it from any route
- `send_trade_alert()` + `send_daily_summary()` both respect the module-level dedup singleton; `reset()` clears it (useful in tests)
- Telegram and email both silently no-op if env vars are missing — safe to call unconditionally
- `_pnl_poller` only polls when `_clients` is non-empty — no wasted CPU when nobody is watching

### Files Phase 6 will touch
- NEW: `backend/analytics/` — portfolio curves, drawdown chart data
- NEW: `backend/scanner/` — market scanner (top gainers, volume spike, breakout)
- `backend/api/routes.py` — admin endpoints: deployments list, audit log viewer, flag toggle
- `backend/api/ws.py` — possibly push scanner results over WebSocket
- Wiring `send_daily_summary()` to an APScheduler job at market close (3:30 PM IST)

### "Don't do this" list
- Do NOT import `aiosmtplib` at module level in `email.py` — it's a lazy import to keep Vercel bundle small
- Do NOT use `asyncio.run()` inside a running event loop for alerts — always use `asyncio.ensure_future()`
- Do NOT remove the `if not _clients: continue` guard in `_pnl_poller` — it prevents unnecessary SQLite reads
