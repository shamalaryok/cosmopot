from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import boto3
import pytest
from httpx import AsyncClient

pytest.importorskip("moto")
from unittest.mock import AsyncMock

from moto import mock_aws  # type: ignore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.generation.enums import GenerationTaskStatus
from backend.generation.models import GenerationTask
from backend.generation.service import resolve_priority
from user_service.enums import SubscriptionStatus, SubscriptionTier, UserRole
from user_service.models import Subscription, User

PNG_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)


@pytest.fixture()
def s3_mock() -> Iterator[None]:
    with mock_aws():
        client = boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="test-access",
            aws_secret_access_key="test-secret",
        )
        client.create_bucket(Bucket="test-generation")
        yield


@pytest.fixture()
def rabbit_stub(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    published: list[dict[str, Any]] = []

    async def _publish(message: Any, routing_key: str) -> None:
        body = message.body.decode("utf-8")
        published.append(
            {
                "priority": message.priority,
                "routing_key": routing_key,
                "payload": json.loads(body),
            }
        )

    channel = AsyncMock()
    exchange = AsyncMock()
    queue = AsyncMock()

    exchange.publish.side_effect = _publish
    channel.declare_exchange.return_value = exchange
    channel.declare_queue.return_value = queue
    channel.set_qos = AsyncMock()
    queue.bind = AsyncMock()

    connection = AsyncMock()
    connection.channel.return_value = channel
    connection.close = AsyncMock()

    async def _connect_stub(url: str) -> Any:  # noqa: ARG001
        return connection

    monkeypatch.setattr(
        "backend.generation.service.aio_pika.connect_robust", _connect_stub
    )

    return {
        "published": published,
        "connection": connection,
        "channel": channel,
        "exchange": exchange,
        "queue": queue,
    }


async def _create_user_with_subscription(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tier: SubscriptionTier = SubscriptionTier.STANDARD,
    quota_limit: int = 5,
    quota_used: int = 0,
) -> User:
    async with session_factory() as session:
        user = User(
            email="user@example.com",
            hashed_password="hashed",
            role=UserRole.USER,
            balance=0,
            is_active=True,
        )
        session.add(user)
        await session.flush()

        subscription = Subscription(
            user_id=user.id,
            tier=tier,
            status=SubscriptionStatus.ACTIVE,
            quota_limit=quota_limit,
            quota_used=quota_used,
            current_period_start=datetime.now(UTC) - timedelta(days=1),
            current_period_end=datetime.now(UTC) + timedelta(days=29),
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio()
async def test_generation_flow_success(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    s3_mock: None,
    rabbit_stub: dict[str, Any],
) -> None:
    user = await _create_user_with_subscription(session_factory)

    payload = {
        "prompt": "Generate a serene landscape",
        "parameters": json.dumps({"width": 256, "height": 256}),
    }
    files = {"file": ("seed.png", PNG_PIXEL, "image/png")}

    response = await async_client.post(
        "/api/v1/generate",
        data=payload,
        files=files,
        headers={"X-User-Id": str(user.id)},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["prompt"] == payload["prompt"]
    assert body["parameters"]["width"] == 256
    assert body["priority"] == resolve_priority("standard")
    assert body["metadata"]["filename"] == "seed.png"

    task_id = UUID(body["task_id"])

    async with session_factory() as session:
        task = await session.get(GenerationTask, task_id)
        assert task is not None
        assert task.status.value == "queued"
        assert task.s3_key.startswith(f"input/{user.id}/")
        assert task.metadata["filename"] == "seed.png"

        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        subscription = result.scalar_one()
        assert subscription.quota_used == 1

    assert len(rabbit_stub["published"]) == 1
    message = rabbit_stub["published"][0]
    assert message["priority"] == resolve_priority("standard")
    assert message["payload"]["task_id"] == str(task_id)

    s3_client = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="test-access",
        aws_secret_access_key="test-secret",
    )
    stored = s3_client.get_object(
        Bucket="test-generation", Key=message["payload"]["s3_key"]
    )
    assert stored["Body"].read() == PNG_PIXEL

    status_response = await async_client.get(
        f"/api/v1/tasks/{task_id}/status",
        headers={"X-User-Id": str(user.id)},
    )
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["status"] == "queued"
    assert status_body["parameters"]["height"] == 256
    assert status_body["metadata"]["filename"] == "seed.png"

    history_response = await async_client.get(
        "/api/v1/generation/tasks",
        params={"page": 1, "page_size": 5},
        headers={"X-User-Id": str(user.id)},
    )
    assert history_response.status_code == 200
    history_body = history_response.json()
    assert history_body["pagination"]["total"] >= 1
    assert history_body["items"][0]["prompt"] == payload["prompt"]


@pytest.mark.asyncio()
async def test_generation_quota_exhausted(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    s3_mock: None,
    rabbit_stub: dict[str, Any],
) -> None:
    user = await _create_user_with_subscription(
        session_factory, quota_limit=1, quota_used=1
    )

    response = await async_client.post(
        "/api/v1/generate",
        data={"prompt": "Another"},
        files={"file": ("seed.png", PNG_PIXEL, "image/png")},
        headers={"X-User-Id": str(user.id)},
    )
    assert response.status_code == 403
    assert not rabbit_stub["published"]


@pytest.mark.asyncio()
async def test_generation_validation_errors(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    s3_mock: None,
    rabbit_stub: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await _create_user_with_subscription(session_factory)

    # Invalid JSON parameters
    response = await async_client.post(
        "/api/v1/generate",
        data={"prompt": "Test", "parameters": "not-json"},
        files={"file": ("seed.png", PNG_PIXEL, "image/png")},
        headers={"X-User-Id": str(user.id)},
    )
    assert response.status_code == 400

    # Unsupported media type
    response = await async_client.post(
        "/api/v1/generate",
        data={"prompt": "Test"},
        files={"file": ("seed.txt", b"hello", "text/plain")},
        headers={"X-User-Id": str(user.id)},
    )
    assert response.status_code == 415

    # Empty prompt
    response = await async_client.post(
        "/api/v1/generate",
        data={"prompt": "   "},
        files={"file": ("seed.png", PNG_PIXEL, "image/png")},
        headers={"X-User-Id": str(user.id)},
    )
    assert response.status_code == 400

    # Oversized payload
    monkeypatch.setattr("backend.api.routes.generation._MAX_IMAGE_BYTES", 10)
    response = await async_client.post(
        "/api/v1/generate",
        data={"prompt": "Big"},
        files={"file": ("seed.png", b"0123456789ABC", "image/png")},
        headers={"X-User-Id": str(user.id)},
    )
    assert response.status_code == 413
    assert not rabbit_stub["published"]


@pytest.mark.asyncio()
async def test_generation_tasks_pagination(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await _create_user_with_subscription(session_factory)
    async with session_factory() as session:
        now = datetime.now(UTC)
        for index in range(12):
            task = GenerationTask(
                id=uuid4(),
                user_id=user.id,
                prompt=f"Task {index}",
                parameters={
                    "width": 512,
                    "height": 512,
                    "model": "stable-diffusion-xl",
                },
                status=GenerationTaskStatus.COMPLETED,
                priority=1,
                subscription_tier="standard",
                s3_bucket="bucket",
                s3_key=f"seed-{index}",
                input_url=f"https://example.com/seed-{index}.png",
                metadata={},
            )
            task.created_at = now + timedelta(seconds=index)
            task.updated_at = task.created_at
            session.add(task)
        await session.commit()

    first_page = await async_client.get(
        "/api/v1/generation/tasks",
        params={"page": 1, "page_size": 5},
        headers={"X-User-Id": str(user.id)},
    )
    assert first_page.status_code == 200
    payload = first_page.json()
    assert payload["pagination"] == {
        "page": 1,
        "page_size": 5,
        "total": 12,
        "has_next": True,
        "has_previous": False,
    }
    assert len(payload["items"]) == 5

    last_page = await async_client.get(
        "/api/v1/generation/tasks",
        params={"page": 3, "page_size": 5},
        headers={"X-User-Id": str(user.id)},
    )
    assert last_page.status_code == 200
    last_payload = last_page.json()
    assert last_payload["pagination"]["page"] == 3
    assert last_payload["pagination"]["has_previous"] is True
    assert last_payload["pagination"]["has_next"] is False
    assert last_payload["pagination"]["total"] == 12
    assert len(last_payload["items"]) == 2
