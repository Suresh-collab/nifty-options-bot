"""0.1 — migration up/down/up cycle + SQLite paper-trade isolation."""
import asyncio
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config.settings import get_settings


def _run_alembic(cmd: str, *args) -> None:
    from alembic import command
    from alembic.config import Config
    cfg = Config("alembic.ini")
    getattr(command, cmd)(cfg, *args)


def test_migration_up_insert_down_table_gone():
    """upgrade → insert row → downgrade → table gone → upgrade to restore."""
    s = get_settings()
    conn_args = {"ssl": "require", "prepared_statement_cache_size": 0, "statement_cache_size": 0}

    async def _check():
        engine = create_async_engine(s.database_migration_url or s.database_url, connect_args=conn_args)
        async with engine.connect() as conn:
            # Insert a row (table was created by previous upgrade)
            await conn.execute(text(
                "INSERT INTO ohlcv_cache (symbol, interval, ts, o, h, l, c, v) "
                "VALUES ('TEST', '1d', NOW(), 1, 2, 0, 1, 500) ON CONFLICT DO NOTHING"
            ))
            await conn.commit()
            r = await conn.execute(text("SELECT COUNT(*) FROM ohlcv_cache WHERE symbol='TEST'"))
            assert r.scalar() >= 1, "Row should exist after upgrade"
        await engine.dispose()

    asyncio.run(_check())

    # Downgrade — all Phase 0 tables dropped
    _run_alembic("downgrade", "base")

    async def _verify_gone():
        engine = create_async_engine(s.database_migration_url or s.database_url, connect_args=conn_args)
        async with engine.connect() as conn:
            r = await conn.execute(text(
                "SELECT EXISTS(SELECT FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='ohlcv_cache')"
            ))
            assert r.scalar() is False, "ohlcv_cache should be gone after downgrade"
        await engine.dispose()

    asyncio.run(_verify_gone())

    # Restore for subsequent tests
    _run_alembic("upgrade", "head")


def test_sqlite_paper_trades_still_accessible():
    """Existing SQLite paper-trade DB must still open after Phase 0 changes."""
    import sqlite3
    import os
    db_path = os.path.join("backend", "paper_trades.db")
    assert os.path.exists(db_path), "paper_trades.db must still exist"
    conn = sqlite3.connect(db_path)
    conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    conn.close()
