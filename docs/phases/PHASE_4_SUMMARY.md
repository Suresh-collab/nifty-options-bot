# Phase 4 Summary — Live Broker Integration (Zerodha)
**Status:** ✅ Complete (sandbox — ENABLE_LIVE_BROKER=false by default)
**Duration:** 2026-05-02
**Completed by:** Claude Sonnet 4.6 agent session

---

## Scope delivered

- [x] 4.1 BrokerAdapter Protocol — `backend/broker/interface.py`; `typing.Protocol` with 5 async methods: `place_order`, `modify_order`, `cancel_order`, `get_positions`, `get_orders`; both adapters satisfy it at runtime
- [x] 4.2 Zerodha Kite Connect adapter — `backend/broker/zerodha_adapter.py`; wraps `kiteconnect.KiteConnect` in executor (non-blocking); maps Kite statuses to canonical states (PLACED/FILLED/REJECTED/CANCELLED)
- [x] 4.3 Paper-vs-live toggle — `ENABLE_LIVE_BROKER=false` always routes to `PaperBrokerAdapter`; `ENABLE_LIVE_BROKER=true` + `BROKER_MODE=live` routes to `ZerodhaKiteAdapter`; `GET /api/broker/status` shows active adapter
- [x] 4.4 Order state machine — `broker_orders` Postgres table; PENDING→PLACED→FILLED/REJECTED/CANCELLED; reject path surfaces reason in API response; audit-logged on every attempt
- [x] 4.5 Encrypted API-key storage — `backend/broker/crypto.py`; Fernet symmetric encryption; per-install salt prepended before encryption; `POST /api/broker/api-keys` stores ciphertext only; plaintext never on disk or in logs
- [x] 4.6 Idempotent order placement — `client_order_id` UUID; `UNIQUE` constraint on `broker_orders.client_order_id`; `ON CONFLICT DO UPDATE` for duplicate submissions; auto-generated if caller omits it
- [x] 4.7 Audit log — every `POST /api/broker/order` and `POST /api/broker/api-keys` writes an immutable `audit_log` row (Phase 0 table); action + payload + actor fields

---

## TDD criteria results

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 4.1 | Contract tests — all 5 methods green on both adapters | ✅ pass | `TestBrokerAdapterContract` (8 tests) |
| 4.2 | place market order → PLACED ack → query orders → FILLED | ✅ pass | `TestZerodhaAdapterSandbox` — mock Kite, COMPLETE status maps to FILLED |
| 4.3 | Flag OFF → paper adapter; flag ON + mode=live → live adapter | ✅ pass | `test_broker_status_*`, `test_get_broker_adapter_*` |
| 4.4 | Reject path → REJECTED in response, audit-logged | ✅ pass | `test_place_order_rejected_*`, `test_place_order_surfaced_in_response` |
| 4.5 | Round-trip: save key → retrieve → plaintext never in storage | ✅ pass | `TestCrypto` (7 tests incl. `test_store_api_keys_endpoint_encrypts`) |
| 4.6 | Duplicate client_order_id → single order in DB (ON CONFLICT) | ✅ pass | `test_idempotent_order_persist_on_conflict`, `test_place_order_generates_client_order_id_if_missing` |
| 4.7 | Every order attempt + API-key store → audit log entry | ✅ pass | `test_audit_log_written_on_place_order`, `test_audit_log_written_on_store_api_keys` |

**Full test run: 119 passed, 1 skipped (DB migration), 0 failures.**

---

## Architecture decisions

- **ADR-017: typing.Protocol for BrokerAdapter** — No ABC inheritance required. Any class with the right async methods is a valid adapter. Makes it trivial to add Angel One / Upstox adapters later (future phase) without touching existing code.
- **ADR-018: kiteconnect in executor** — `kiteconnect.KiteConnect` is synchronous. Running in `asyncio.get_event_loop().run_in_executor(None, ...)` keeps the FastAPI event loop non-blocking. Phase 5 (WebSocket) will move to the async Kite streaming API.
- **ADR-019: kiteconnect as lazy optional import** — Only imported inside `ZerodhaKiteAdapter.__init__`. If kiteconnect is not installed, the exception is clear and only raised when live mode is actually requested.
- **ADR-020: In-memory credential store** — `_broker_credentials` in routes.py resets on restart. Acceptable for sandbox/demo. Production deployment (Phase 5+) should persist encrypted credentials to DB.
- **ADR-021: ON CONFLICT for idempotency** — `broker_orders.client_order_id` has a UNIQUE constraint. The `_persist_order` helper uses `ON CONFLICT DO UPDATE` so duplicate submissions update the existing row rather than failing.

---

## New files created

```
backend/broker/__init__.py
backend/broker/interface.py          BrokerAdapter Protocol + OrderRequest/Result/Position/Order
backend/broker/paper_adapter.py      Wraps simulator.py — satisfies BrokerAdapter
backend/broker/zerodha_adapter.py    Wraps kiteconnect.KiteConnect — satisfies BrokerAdapter
backend/broker/crypto.py             Fernet encrypt/decrypt + key generation
backend/models/orders.py             BrokerOrder SQLAlchemy model
backend/migrations/versions/004_add_orders_table.py
tests/test_broker.py                 28 tests — all 7 TDD criteria
```

## Modified files

```
backend/config/settings.py     + broker_mode, broker_encryption_key, broker_salt
backend/requirements.txt       + kiteconnect>=4.2.0, cryptography>=42.0.0
backend/api/routes.py          + _broker_credentials, _get_broker_adapter(),
                                 _persist_order(), _audit_order(),
                                 GET  /broker/status
                                 POST /broker/api-keys
                                 POST /broker/order
                                 DELETE /broker/order/{id}
                                 GET  /broker/orders
                                 GET  /broker/positions
backend/.env.example           + BROKER_MODE, BROKER_ENCRYPTION_KEY, BROKER_SALT
```

---

## Test counts

| Suite | Tests | Status |
|---|---|---|
| Backend pytest | 119 | All green (1 skipped = DB migration) |
| Frontend vitest | 11 | All green (unchanged) |

---

## Known risks / debt opened

- **In-memory credentials** — `_broker_credentials` lost on restart. Must persist to DB (encrypted) before production use.
- **No Kite token refresh** — Zerodha access tokens expire daily. Phase 5 needs a token-refresh flow (`generate_session` + webhook or cron).
- **`ENABLE_LIVE_BROKER=false` is the only real-money guard** — Until Phases 0–4 paper validation is signed off by user, this flag stays false. Flipping it is an explicit, manual, irreversible user action.
- **No webhook handler** — Kite sends order updates via postback webhook. Phase 5 should add `POST /api/broker/webhook` to update order status from PLACED → FILLED/REJECTED in real time.
- **broker_orders.updated_at** — `onupdate=datetime.utcnow` works for ORM updates but not raw SQL `_persist_order`. Phase 5 should add a Postgres trigger for `updated_at`.

---

## Handoff to Phase 5

### Context the next agent must know
- `ENABLE_LIVE_BROKER=false` is default and MUST stay false until user explicitly activates
- `_get_broker_adapter()` in routes.py is the single dispatch point — extend here for new brokers
- `_broker_credentials` dict in routes.py holds Fernet tokens (not plaintext)
- `kiteconnect` is only imported inside `ZerodhaKiteAdapter.__init__` — never at module level
- `broker_orders` table has `UNIQUE(client_order_id)` — always pass a UUID to prevent phantom duplicates
- Audit log uses existing Phase 0 `audit_log` table — no schema changes needed

### Files Phase 5 will touch
- NEW: `backend/api/ws.py` — WebSocket endpoint for live P&L + position updates
- NEW: `backend/notifications/telegram.py` — Telegram bot alerts
- NEW: `backend/notifications/email.py` — daily summary email
- `backend/api/routes.py` — `POST /broker/webhook` for Kite order postbacks
- `backend/broker/zerodha_adapter.py` — add `KiteTicker` streaming in Phase 5

### "Don't do this" list
- Do NOT store plaintext API keys anywhere — always encrypt with `broker/crypto.py`
- Do NOT call `kiteconnect.KiteConnect` directly in routes — always go through `_get_broker_adapter()`
- Do NOT flip `ENABLE_LIVE_BROKER=true` before paper P&L has been observed for ≥ 3 days (Phase 3 exit gate)
