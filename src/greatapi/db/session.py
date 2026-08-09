"""Async engine and session management.

The engine is built lazily on first use rather than at import time. That is what
lets tests, the CLI and the job worker retarget the database without patching
module globals, and it keeps ``import greatapi`` from opening a connection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from greatapi.conf.settings import get_settings

__all__ = [
    "configure_engine",
    "create_all",
    "dispose_engine",
    "get_engine",
    "get_session",
    "get_sessionmaker",
    "session_scope",
]

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_configured_url: str | None = None


def _build_engine(url: str, **overrides: Any) -> AsyncEngine:
    settings = get_settings()
    kwargs: dict[str, Any] = {"echo": settings.database_echo, "future": True}

    if url.startswith("sqlite"):
        # aiosqlite runs on a worker thread per connection, so the default
        # single-thread check has to go. An in-memory database additionally
        # needs one shared connection or every session sees an empty schema.
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url or url.endswith("://"):
            kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_max_overflow
        kwargs["pool_pre_ping"] = True

    kwargs.update(overrides)
    engine = create_async_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def configure_engine(url: str | None = None, **overrides: Any) -> AsyncEngine:
    """Build (or rebuild) the engine, optionally pointing at a different URL."""
    global _engine, _sessionmaker, _configured_url
    _configured_url = url or get_settings().database_url
    _engine = _build_engine(_configured_url, **overrides)
    _sessionmaker = async_sessionmaker(
        bind=_engine, expire_on_commit=False, autoflush=False, class_=AsyncSession
    )
    return _engine


def get_engine() -> AsyncEngine:
    """Return the process-wide engine, creating it on first use."""
    if _engine is None or _configured_url != get_settings().database_url:
        return configure_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def dispose_engine() -> None:
    """Close every pooled connection. Called on application shutdown."""
    global _engine, _sessionmaker, _configured_url
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
    _configured_url = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session.

    The session is rolled back on error and always closed, so a failed request
    can never leak a dirty session into the pool.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Session context manager for code outside a request (CLI, jobs, startup).

    Commits on success, rolls back on error.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def create_all() -> None:
    """Create every framework and application table.

    Convenient for tests and the quickstart; real deployments should use
    ``greatapi migrate`` so schema changes are versioned.
    """
    from greatapi.db.base import Base

    async with get_engine().begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
