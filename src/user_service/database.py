from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Create an async engine for the given database URL."""

    url_obj = make_url(url)
    is_sqlite = url_obj.get_backend_name().startswith("sqlite")

    connect_args: dict[str, Any] = {}
    if is_sqlite:
        connect_args["timeout"] = 30

    engine_kwargs: dict[str, Any] = {
        "echo": echo,
        "future": True,
        "pool_pre_ping": True,
    }
    if connect_args:
        engine_kwargs["connect_args"] = connect_args

    engine = create_async_engine(url, **engine_kwargs)

    if is_sqlite:

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA journal_mode=WAL")
            finally:
                cursor.close()

    return engine


def create_session_factory(
    engine: AsyncEngine, *, expire_on_commit: bool = False
) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory bound to the provided engine."""

    return async_sessionmaker(engine, expire_on_commit=expire_on_commit)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Simple async context manager yielding a session and guaranteeing cleanup."""

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
