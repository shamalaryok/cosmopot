from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.testclient import TestClient, WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from backend.generation.enums import GenerationTaskStatus
from backend.generation.models import GenerationTask
from user_service.enums import UserRole
from user_service.models import User


@pytest.fixture()
def test_client(
    app: FastAPI, event_loop: asyncio.AbstractEventLoop
) -> Iterator[TestClient]:
    client = TestClient(app)
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        event_loop.run_until_complete(redis.flushdb())
    try:
        yield client
    finally:
        if redis is not None:
            event_loop.run_until_complete(redis.flushdb())
        client.close()


async def _create_user_and_task(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    status: GenerationTaskStatus = GenerationTaskStatus.QUEUED,
) -> tuple[User, GenerationTask]:
    async with session_factory() as session:
        user = User(
            email="ws-user@example.com",
            hashed_password="hashed",
            role=UserRole.USER,
            balance=0,
            is_active=True,
        )
        session.add(user)
        await session.flush()

        task = GenerationTask(
            user_id=user.id,
            prompt="Generate via websocket",
            parameters={"width": 512},
            status=status,
            priority=1,
            subscription_tier="basic",
            s3_bucket="bucket",
            s3_key="key",
            input_url=None,
            metadata={"source": "test"},
        )
        session.add(task)
        await session.commit()
        await session.refresh(user)
        await session.refresh(task)

        await app.state.task_broadcaster.publish(task)
        return user, task


async def _set_task_status(
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    task_id: UUID,
    *,
    status: GenerationTaskStatus,
    error: str | None = None,
) -> GenerationTask:
    async with session_factory() as session:
        task = await session.get(GenerationTask, task_id)
        assert task is not None
        task.status = status
        task.error_message = error
        await session.commit()
        await session.refresh(task)
        await app.state.task_broadcaster.publish(task)
        return task


def _receive_non_heartbeat(ws: WebSocketTestSession) -> Mapping[str, Any]:
    while True:
        message = ws.receive_json()
        assert isinstance(message, dict)
        if message.get("type") != "heartbeat":
            return message


def test_websocket_requires_authentication(test_client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as disconnect:
        with test_client.websocket_connect(f"/ws/tasks/{uuid4()}"):
            pass
    assert disconnect.value.code == status.WS_1008_POLICY_VIOLATION


def test_websocket_streams_updates_in_order(
    test_client: TestClient,
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    event_loop: asyncio.AbstractEventLoop,
) -> None:
    user, task = event_loop.run_until_complete(
        _create_user_and_task(app, session_factory)
    )

    with test_client.websocket_connect(
        f"/ws/tasks/{task.id}",
        headers={"X-User-Id": str(user.id)},
    ) as ws:
        initial = _receive_non_heartbeat(ws)
        assert initial["type"] == "snapshot"
        assert initial["status"] == GenerationTaskStatus.QUEUED.value
        assert initial["sequence"] == 1
        assert initial["terminal"] is False

        event_loop.run_until_complete(
            _set_task_status(
                app, session_factory, task.id, status=GenerationTaskStatus.PROCESSING
            )
        )
        processing = _receive_non_heartbeat(ws)
        assert processing["type"] == "update"
        assert processing["sequence"] == 2
        assert processing["status"] == GenerationTaskStatus.PROCESSING.value
        assert processing["terminal"] is False

        event_loop.run_until_complete(
            _set_task_status(
                app, session_factory, task.id, status=GenerationTaskStatus.COMPLETED
            )
        )
        completed = _receive_non_heartbeat(ws)
        assert completed["terminal"] is True
        assert completed["status"] == GenerationTaskStatus.COMPLETED.value

        with pytest.raises(WebSocketDisconnect) as disconnect:
            while True:
                message = ws.receive_json()
                if message.get("type") == "heartbeat":
                    continue
                pytest.fail(f"Unexpected message after websocket completion: {message}")
        assert disconnect.value.code == status.WS_1000_NORMAL_CLOSURE


def test_websocket_snapshot_reflects_latest_state(
    test_client: TestClient,
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    event_loop: asyncio.AbstractEventLoop,
) -> None:
    user, task = event_loop.run_until_complete(
        _create_user_and_task(app, session_factory)
    )
    event_loop.run_until_complete(
        _set_task_status(
            app,
            session_factory,
            task.id,
            status=GenerationTaskStatus.FAILED,
            error="model divergence",
        )
    )

    with test_client.websocket_connect(
        f"/ws/tasks/{task.id}",
        headers={"X-User-Id": str(user.id)},
    ) as ws:
        snapshot = _receive_non_heartbeat(ws)
        assert snapshot["type"] == "snapshot"
        assert snapshot["status"] == GenerationTaskStatus.FAILED.value
        assert snapshot["terminal"] is True
        assert snapshot["error"] == "model divergence"
        assert snapshot["sequence"] == 2

        with pytest.raises(WebSocketDisconnect) as disconnect:
            while True:
                message = ws.receive_json()
                if message.get("type") == "heartbeat":
                    continue
                pytest.fail(f"Unexpected message after websocket completion: {message}")
        assert disconnect.value.code == status.WS_1000_NORMAL_CLOSURE
