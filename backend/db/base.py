from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.config.settings import get_settings


class Base(DeclarativeBase):
    pass


def _connect_args() -> dict:
    # Neon free tier uses PgBouncer in transaction mode.
    # prepared_statement_cache_size=0 prevents "prepared statement already exists" errors.
    return {
        "ssl": "require",
        "prepared_statement_cache_size": 0,
        "statement_cache_size": 0,
    }


def get_engine() -> AsyncEngine:
    s = get_settings()
    return create_async_engine(
        s.database_url,
        echo=(s.log_level.upper() == "DEBUG"),
        connect_args=_connect_args(),
        pool_pre_ping=True,
    )


def get_migration_engine() -> AsyncEngine:
    """Direct (non-pooler) engine for Alembic — avoids PgBouncer DDL issues."""
    s = get_settings()
    url = s.database_migration_url or s.database_url
    return create_async_engine(url, connect_args=_connect_args(), pool_pre_ping=True)


def get_session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker:
    if engine is None:
        engine = get_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
