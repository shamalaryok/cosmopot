from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .banana import GeminiNanoClient
from .config import RuntimeOverrides, WorkerSettings
from .db import (
    configure_session_factory,
    create_engine,
    dispose_engine,
    use_session_factory,
)
from .logging import configure_logging, get_logger
from .redis_events import RedisNotifier
from .storage import MinioStorage, StorageClient


@dataclass(slots=True)
class RuntimeState:
    settings: WorkerSettings
    session_factory: async_sessionmaker[AsyncSession]
    engine: AsyncEngine | None
    storage: StorageClient
    notifier: RedisNotifier
    banana_client: GeminiNanoClient


_state: RuntimeState | None = None
_state_lock = asyncio.Lock()
_log = get_logger(__name__)


async def initialise(overrides: RuntimeOverrides | None = None) -> RuntimeState:
    global _state
    async with _state_lock:
        if _state is not None:
            return _state

        overrides = overrides or RuntimeOverrides()
        settings = overrides.settings or WorkerSettings()
        configure_logging(overrides.log_level or settings.log_level)

        managed_engine: AsyncEngine | None = None

        if overrides.session_factory is not None:
            session_factory = overrides.session_factory
            bound_engine = getattr(session_factory, "bind", None)
            engine_for_scope = (
                bound_engine if isinstance(bound_engine, AsyncEngine) else None
            )
            use_session_factory(session_factory, engine=engine_for_scope)
        else:
            managed_engine = create_engine(settings.database_url)
            session_factory = configure_session_factory(managed_engine)
            use_session_factory(session_factory, engine=managed_engine)

        storage: StorageClient
        if overrides.storage is not None:
            storage = overrides.storage
        else:
            storage = MinioStorage.from_settings(settings)

        if overrides.banana_client is not None:
            banana_client = overrides.banana_client
        else:
            banana_client = GeminiNanoClient.from_settings(settings)

        if overrides.notifier is not None:
            notifier = overrides.notifier
        else:
            notifier = RedisNotifier.from_settings(settings)
            await notifier.connect()

        _state = RuntimeState(
            settings=settings,
            session_factory=session_factory,
            engine=managed_engine,
            storage=storage,
            notifier=notifier,
            banana_client=banana_client,
        )
        _log.info("worker-runtime-initialised")
        return _state


async def shutdown() -> None:
    global _state
    async with _state_lock:
        if _state is None:
            return
        state = _state
        _state = None

        await state.notifier.close()
        state.banana_client.close()
        if state.engine is not None:
            await dispose_engine()
        _log.info("worker-runtime-shutdown")


def get_runtime() -> RuntimeState:
    state = _state
    if state is None:
        raise RuntimeError("Worker runtime has not been initialised")
    return state
