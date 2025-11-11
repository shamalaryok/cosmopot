from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from redis.asyncio import Redis

from .config import WorkerSettings
from .logging import get_logger


class RedisNotifier:
    """Publishes status transitions and manages idempotency locks."""

    def __init__(
        self,
        url: str,
        *,
        status_channel: str,
        dead_letter_channel: str,
        idempotency_prefix: str,
        idempotency_ttl: int,
    ) -> None:
        self._url = url
        self._status_channel = status_channel
        self._dead_letter_channel = dead_letter_channel
        self._idempotency_prefix = idempotency_prefix
        self._idempotency_ttl = idempotency_ttl
        self._client: Redis[str] | None = None
        self._log = get_logger(__name__)

    @classmethod
    def from_settings(cls, settings: WorkerSettings) -> RedisNotifier:
        return cls(
            settings.redis_pubsub_url,
            status_channel=settings.redis_status_channel,
            dead_letter_channel=settings.redis_dead_letter_channel,
            idempotency_prefix=settings.redis_idempotency_prefix,
            idempotency_ttl=settings.redis_idempotency_ttl_seconds,
        )

    async def connect(self) -> None:
        if self._client is None:
            self._client = cast(
                Redis[str],
                Redis.from_url(
                    self._url,
                    encoding="utf-8",
                    decode_responses=True,
                    health_check_interval=30,
                ),
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _get_client(self) -> Redis[str]:
        client = self._client
        if client is None:
            raise RuntimeError("Redis client is not ready")
        return client

    async def publish_status(self, status: str, payload: dict[str, Any]) -> None:
        message = {
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        await self._get_client().publish(self._status_channel, json.dumps(message))

    async def publish_dead_letter(self, payload: dict[str, Any]) -> None:
        message = {
            "status": "dead_letter",
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        await self._get_client().publish(self._dead_letter_channel, json.dumps(message))

    def _idempotency_key(self, task_id: int) -> str:
        return f"{self._idempotency_prefix}:{task_id}"

    async def acquire_task(self, task_id: int) -> bool:
        key = self._idempotency_key(task_id)
        result = await self._get_client().set(
            key, "1", nx=True, ex=self._idempotency_ttl
        )
        return bool(result)

    async def release_task(self, task_id: int) -> None:
        await self._get_client().delete(self._idempotency_key(task_id))
