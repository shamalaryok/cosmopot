from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.config import Settings, get_settings

_ENGINE: AsyncEngine | None = None
_SESSION_FACTORY: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _ENGINE
    if _ENGINE is None:
        settings = settings or get_settings()
        _ENGINE = create_async_engine(
            settings.database.dsn,
            echo=settings.database.echo,
            pool_pre_ping=True,
        )
    return _ENGINE


def get_session_factory(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = async_sessionmaker(
            get_engine(settings),
            expire_on_commit=False,
            autoflush=False,
        )
    return _SESSION_FACTORY


async def get_session() -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def dispose_engine() -> None:
    global _ENGINE, _SESSION_FACTORY

    if _SESSION_FACTORY is not None:
        _SESSION_FACTORY = None

    if _ENGINE is None:
        return

    await _ENGINE.dispose()
    _ENGINE = None
