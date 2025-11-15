from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import structlog
from redis.asyncio import Redis

from backend.generation.enums import GenerationTaskStatus
from backend.generation.models import GenerationTask

__all__ = ["TaskStatusBroadcaster"]

logger = structlog.get_logger(__name__)

_TERMINAL_STATUSES = {
    GenerationTaskStatus.COMPLETED,
    GenerationTaskStatus.FAILED,
}
_STATE_TTL_SECONDS = 3600


class TaskStatusBroadcaster:
    """Publish generation task lifecycle updates over Redis pub/sub."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish(
        self, task: GenerationTask, *, event: str = "update"
    ) -> dict[str, Any]:
        """Serialize state for reconnects and publish updates to subscribers."""

        payload = await self._build_payload(task, event=event)
        await self._store_state(task.id, payload)

        channel = self.channel_name(task.id)
        encoded = json.dumps(payload)
        await self._redis.publish(channel, encoded)
        logger.debug(
            "task_status_published",
            channel=channel,
            sequence=payload["sequence"],
            status=payload["status"],
        )
        return payload

    async def snapshot(self, task: GenerationTask) -> dict[str, Any]:
        """Return the latest persisted payload for the task, or build one on the fly."""

        latest = await self.latest(task.id)
        if latest is not None:
            snapshot = dict(latest)
            snapshot["type"] = "snapshot"
            snapshot["sent_at"] = _timestamp()
            return snapshot

        payload = self._serialize_task(task)
        payload.update(
            {
                "type": "snapshot",
                "sequence": 0,
                "terminal": task.status in _TERMINAL_STATUSES,
                "sent_at": _timestamp(),
            }
        )
        return payload

    async def latest(self, task_id: UUID) -> dict[str, Any] | None:
        raw = await self._redis.get(self._state_key(task_id))
        if raw is None:
            return None
        loaded = json.loads(raw)
        if not isinstance(loaded, dict):  # pragma: no cover - defensive guard
            raise ValueError("Stored task payload must be a mapping")
        return cast(dict[str, Any], loaded)

    async def reset(self, task_id: UUID) -> None:
        await self._redis.delete(self._state_key(task_id), self._sequence_key(task_id))

    @staticmethod
    def channel_name(task_id: UUID | str) -> str:
        return f"tasks:{task_id}"

    @staticmethod
    def _state_key(task_id: UUID | str) -> str:
        return f"tasks:{task_id}:state"

    @staticmethod
    def _sequence_key(task_id: UUID | str) -> str:
        return f"tasks:{task_id}:sequence"

    async def _store_state(self, task_id: UUID, payload: Mapping[str, Any]) -> None:
        encoded = json.dumps(dict(payload))
        await self._redis.set(self._state_key(task_id), encoded, ex=_STATE_TTL_SECONDS)
        await self._redis.expire(self._sequence_key(task_id), _STATE_TTL_SECONDS)

    async def _build_payload(
        self, task: GenerationTask, *, event: str
    ) -> dict[str, Any]:
        serialised = self._serialize_task(task)
        sequence = await self._redis.incr(self._sequence_key(task.id))
        serialised.update(
            {
                "type": event,
                "sequence": sequence,
                "terminal": task.status in _TERMINAL_STATUSES,
                "sent_at": _timestamp(),
            }
        )
        return serialised

    @staticmethod
    def _serialize_task(task: GenerationTask) -> dict[str, Any]:
        return {
            "task_id": str(task.id),
            "status": task.status.value,
            "prompt": task.prompt,
            "parameters": dict(task.parameters or {}),
            "priority": task.priority,
            "subscription_tier": task.subscription_tier,
            "input_url": task.input_url,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "metadata": dict(task.metadata_dict),
            "error": task.error_message,
        }


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
