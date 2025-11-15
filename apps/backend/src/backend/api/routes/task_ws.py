from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import structlog
from fastapi import APIRouter, status
from fastapi.websockets import WebSocket, WebSocketDisconnect
from redis.asyncio.client import PubSub, Redis
from starlette.websockets import WebSocketState

from backend.db.session import get_session_factory
from backend.generation.broadcaster import TaskStatusBroadcaster
from backend.generation.models import GenerationTask
from user_service.repository import get_user_with_related

router = APIRouter(prefix="/ws", tags=["tasks"])
logger = structlog.get_logger(__name__)

_HEARTBEAT_INTERVAL = 15.0
_INACTIVITY_TIMEOUT = 60.0


@router.websocket("/tasks/{task_id}")
async def task_updates(websocket: WebSocket, task_id: UUID) -> None:
    redis_maybe = getattr(websocket.app.state, "redis", None)
    broadcaster_maybe: TaskStatusBroadcaster | None = getattr(
        websocket.app.state, "task_broadcaster", None
    )
    if redis_maybe is None or broadcaster_maybe is None:
        await _reject_websocket(
            websocket,
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Task updates unavailable",
        )
        return

    redis = cast(Redis, redis_maybe)
    broadcaster = broadcaster_maybe

    user_id: int | None = None

    user_id_header = websocket.headers.get("x-user-id")
    if user_id_header is not None:
        try:
            user_id = int(user_id_header)
        except ValueError:
            await _reject_websocket(
                websocket,
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Invalid authentication header",
            )
            return
    else:
        user_id = _user_id_from_session(websocket)
    if user_id is None:
        await _reject_websocket(
            websocket,
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing authentication context",
        )
        return

    assert user_id is not None

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await get_user_with_related(session, user_id)
        if user is None or not user.is_active or user.deleted_at is not None:
            await _reject_websocket(
                websocket,
                code=status.WS_1008_POLICY_VIOLATION,
                reason="User not authorised",
            )
            return

        assert user is not None

        task = await session.get(GenerationTask, task_id)
        if task is None or task.user_id != user.id:
            await _reject_websocket(
                websocket,
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Task not found",
            )
            return

        assert task is not None

        await session.refresh(task)
        snapshot = await broadcaster.snapshot(task)

    await websocket.accept()
    await websocket.send_json(snapshot)

    if snapshot.get("terminal"):
        await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
        logger.info("task_ws_terminal_snapshot", task_id=str(task_id), user_id=user_id)
        return

    channel = TaskStatusBroadcaster.channel_name(task_id)
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    logger.info("task_ws_connected", task_id=str(task_id), user_id=user_id)

    last_activity = time.monotonic()

    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=_HEARTBEAT_INTERVAL
                    ),
                    timeout=_INACTIVITY_TIMEOUT,
                )
            except TimeoutError:
                idle = time.monotonic() - last_activity
                if idle >= _INACTIVITY_TIMEOUT:
                    await websocket.close(
                        code=status.WS_1011_INTERNAL_ERROR,
                        reason="Task updates timed out",
                    )
                    logger.warning(
                        "task_ws_timeout", task_id=str(task_id), user_id=user_id
                    )
                    break

                sent = await _send_safe(websocket, _heartbeat_payload())
                if not sent:
                    logger.info(
                        "task_ws_heartbeat_skipped",
                        task_id=str(task_id),
                        user_id=user_id,
                    )
                    break
                last_activity = time.monotonic()
                continue

            if message is None:
                sent = await _send_safe(websocket, _heartbeat_payload())
                if not sent:
                    logger.info(
                        "task_ws_heartbeat_skipped",
                        task_id=str(task_id),
                        user_id=user_id,
                    )
                    break
                last_activity = time.monotonic()
                continue

            payload = _decode_pubsub_message(message)
            if payload is None:
                continue

            sent = await _send_safe(websocket, payload)
            if not sent:
                logger.info(
                    "task_ws_send_failed", task_id=str(task_id), user_id=user_id
                )
                break
            last_activity = time.monotonic()

            if payload.get("terminal"):
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                logger.info(
                    "task_ws_terminal_update", task_id=str(task_id), user_id=user_id
                )
                break
    except WebSocketDisconnect:
        logger.info(
            "task_ws_client_disconnected", task_id=str(task_id), user_id=user_id
        )
    finally:
        await _close_pubsub(pubsub, channel)


async def _close_pubsub(pubsub: PubSub, channel: str) -> None:
    try:
        await pubsub.unsubscribe(channel)
    except Exception as exc:  # pragma: no cover - defensive cleanup
        logger.debug("task_ws_unsubscribe_failed", channel=channel, error=str(exc))
    finally:
        await pubsub.close()


def _user_id_from_session(websocket: WebSocket) -> int | None:
    # Check if session is in scope to avoid triggering SessionMiddleware assertion
    if "session" not in websocket.scope:
        return None
    session_data = websocket.scope.get("session")
    if isinstance(session_data, Mapping):
        auth = session_data.get("auth")
        if isinstance(auth, Mapping):
            return _coerce_user_id(auth.get("user_id"))
    return None


def _coerce_user_id(candidate: Any) -> int | None:
    if isinstance(candidate, int):
        return candidate
    if isinstance(candidate, str) and candidate.isdigit():
        return int(candidate)
    return None


async def _reject_websocket(
    websocket: WebSocket, *, code: int, reason: str | None = None
) -> None:
    if websocket.client_state is WebSocketState.DISCONNECTED:
        return
    try:
        await websocket.close(code=code, reason=reason)
    except RuntimeError:
        return


async def _send_safe(websocket: WebSocket, payload: dict[str, Any]) -> bool:
    if websocket.client_state is not WebSocketState.CONNECTED:
        return False
    try:
        await websocket.send_json(payload)
    except WebSocketDisconnect:
        raise
    except RuntimeError:
        return False
    return True


def _decode_pubsub_message(message: dict[str, Any]) -> dict[str, Any] | None:
    data = message.get("data")
    if data is None:
        return None
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    try:
        parsed = json.loads(data)
    except (TypeError, json.JSONDecodeError):
        logger.warning("task_ws_invalid_payload", raw=data)
        return None
    if not isinstance(parsed, dict):
        logger.warning("task_ws_unexpected_payload_type", raw=parsed)
        return None
    typed: dict[str, Any] = parsed
    typed.setdefault("type", "update")
    return typed


def _heartbeat_payload() -> dict[str, Any]:
    return {
        "type": "heartbeat",
        "sent_at": datetime.now(UTC).isoformat(),
    }
