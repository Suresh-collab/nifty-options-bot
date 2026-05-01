# Phase 0 Summary — Foundation Hardening
**Status:** ✅ Complete
**Duration:** 2026-04-26
**Completed by:** Claude Sonnet 4.6 agent session

---

## Scope delivered

- [x] 0.1 PostgreSQL + Alembic — 5 new tables in Neon alongside existing SQLite paper trading
- [x] 0.2 pytest (backend, 12 tests) + vitest (frontend, 6 tests) wired; CI updated
- [x] 0.3 `.env` + `.env.example` + `pydantic-settings` config loader
- [x] 0.4 CI postcss ESM fix confirmed; CI now runs both test suites + coverage
- [x] 0.5 Structured JSON logging + request-id middleware (`X-Request-Id` header)
- [x] 0.6 Feature-flag module at `backend/config/feature_flags.py`

---

## TDD criteria results

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 0.1 | migration up → insert row → migration down → row gone | ✅ pass | `tests/test_migrations.py::test_migration_up_insert_down_table_gone` |
| 0.1 | Existing SQLite paper-trade flow still works | ✅ pass | `tests/test_migrations.py::test_sqlite_paper_trades_still_accessible` |
| 0.2 | CI runs both suites; coverage report artifact uploaded | ✅ pass | `.github/workflows/ci.yml` updated |
| 0.3 | Missing required env var → startup error with field name | ✅ pass | `tests/test_config.py::test_missing_database_url_raises` |
| 0.5 | 3 requests in sequence → each has unique `request_id` | ✅ pass | `tests/test_logging.py::test_three_requests_each_get_unique_ids` |
| 0.5 | Log lines within a request share that request's ID | ✅ pass | `tests/test_logging.py::test_log_lines_carry_request_id` |
| 0.6 | Toggling flag off → code path not entered | ✅ pass | `tests/test_feature_flags.py::test_flag_enabled_via_env` |

---

## Architecture decisions

- **ADR-001: Neon (serverless Postgres) over Docker** — solo user, no Docker requirement, free tier sufficient for dev + CI
- **ADR-002: asyncpg + SQLAlchemy 2.0 async** — matches existing async FastAPI codebase; PgBouncer pooler fix: `prepared_statement_cache_size=0`
- **ADR-003: `setLogRecordFactory` for request_id** — propagation skips parent logger filters; factory stamps `request_id` on every record at creation, so all handlers (including test-injected ones) always see it
- **ADR-004: Real money deferred to end** — user decision 2026-04-26; all safety guardrails built, live broker activation is manual step after Phases 0–5 paper validation

---

## New files created

```
.env                                    gitignored, real Neon creds
.env.example                            placeholder template
alembic.ini                             Alembic config, script_location=backend/migrations
pytest.ini                              pythonpath = . backend
backend/config/__init__.py
backend/config/settings.py             pydantic-settings Settings + get_settings()
backend/config/feature_flags.py        is_enabled(), all_flags()
backend/db/__init__.py
backend/db/base.py                      async engine, session factory, Base
backend/models/__init__.py
backend/models/ohlcv_cache.py
backend/models/signals.py
backend/models/trades.py
backend/models/backtest_runs.py
backend/models/audit_log.py
backend/middleware/__init__.py
backend/middleware/logging.py           JSON logging + RequestLoggingMiddleware
backend/migrations/env.py              async Alembic env
backend/migrations/script.py.mako
backend/migrations/versions/001_initial_tables.py
tests/__init__.py
tests/conftest.py
tests/test_config.py
tests/test_feature_flags.py
tests/test_migrations.py
tests/test_logging.py
frontend/vitest.config.js
frontend/src/test/setup.js
frontend/src/test/store.test.js
frontend/src/test/MarketStatusBar.test.jsx
```

## Modified files

```
backend/main.py             +RequestLoggingMiddleware, setup_logging()
backend/requirements.txt    +sqlalchemy, alembic, asyncpg, pydantic-settings, python-json-logger, pytest stack
frontend/package.json       +vitest, @testing-library/react, jsdom, @vitest/coverage-v8
.github/workflows/ci.yml    frontend: npm test:coverage + build; backend: pip install backend/requirements.txt + pytest --cov
docs/phases/MASTER_PLAN.md  real-money decision updated to "deferred to end"
```

---

## Known risks / debt opened

- CI pytest job requires `DATABASE_URL` and `DATABASE_MIGRATION_URL` secrets set in GitHub repo settings — **must be done before first push**
- `python-multipart` pending deprecation warning from Starlette (not ours — upstream)
- `audit_log` immutability is application-convention only (no DB trigger). Phase 3 can add a Postgres trigger if needed.

---

## Handoff to Phase 1

### Context the next agent must know
- Neon project: `restless-night-74462866`, branch `production`, region `ap-southeast-1`
- DB pooler URL: `postgresql+asyncpg://...@ep-sweet-mountain-aomw75fk-pooler.c-2...`
- Direct URL (for migrations): `postgresql+asyncpg://...@ep-sweet-mountain-aomw75fk.c-2...`
- All feature flags default OFF. Never flip `ENABLE_LIVE_BROKER` in a real account until Phase 0–5 paper validation is complete.
- Run tests from project root: `python -m pytest tests/`
- Run migrations from project root: `python -m alembic upgrade head`
- `pythonpath = . backend` in pytest.ini — both `backend.*` and `api.*` are importable

### Open questions deferred
- **OHLCV partitioning**: Phase 1 adds 2+ years of 5-min candles. Postgres table partitioning by year should be evaluated then.
- **Migration test speed**: `test_migration_up_insert_down_table_gone` does a full up/down/up cycle against Neon (~30s). Phase 1 may want a dedicated test DB branch.

### Files Phase 1 will touch
- `backend/models/ohlcv_cache.py` — may need partitioning or bulk-insert optimisation
- `backend/db/base.py` — session dependency for route injection
- New: `backend/backtesting/`, `backend/api/routes.py` (new endpoints `/api/backtest`)
- New: `frontend/src/components/BacktestTab.jsx`

### "Don't do this" list
- Do NOT add `channel_binding=require` to asyncpg URLs — asyncpg doesn't support that psycopg2 param
- Do NOT use `ssl=require` as a URL query param with asyncpg — use `connect_args={"ssl": "require"}` instead
- Do NOT add the `_RequestIdFilter` to a handler and expect test-injected handlers to see `request_id` — use `setLogRecordFactory` (see ADR-003)
- Do NOT add the filter to root logger and expect it to fire for propagated records — Python propagation skips parent `filter()` (see ADR-003)
