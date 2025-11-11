from __future__ import annotations

import asyncio
from typing import Any

from psycopg_pool import AsyncConnectionPool

from .config import settings

_db_pool: AsyncConnectionPool | None = None


async def init_pool() -> None:
    global _db_pool
    if _db_pool is not None:
        return

    _db_pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=1,
        max_size=10,
        open=False,
    )
    await _db_pool.open()


async def close_pool() -> None:
    global _db_pool
    pool = _db_pool
    if pool is None:
        return
    await pool.close()
    _db_pool = None


async def execute(query: str, *args: Any) -> None:
    pool = _db_pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, args)


async def fetchval(query: str, *args: Any) -> Any:
    pool = _db_pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, args)
            row = await cur.fetchone()

    return row[0] if row else None


async def healthcheck() -> bool:
    pool = _db_pool
    if pool is None:
        raise RuntimeError("Database pool is not initialized")

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1")
    return True


async def wait_for_database(timeout_seconds: float = 30.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while True:
        try:
            await init_pool()
            await healthcheck()
            return
        except Exception:  # pragma: no cover - startup retry logic
            if asyncio.get_event_loop().time() >= deadline:
                raise
            await asyncio.sleep(1)
