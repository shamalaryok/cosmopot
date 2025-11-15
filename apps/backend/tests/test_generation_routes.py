from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.generation.enums import GenerationTaskStatus
from backend.generation.models import GenerationTask
from user_service.enums import UserRole
from user_service.models import User


async def _create_user_with_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[User, str]:
    """Create a user and return user object and access token."""
    async with session_factory() as session:
        user = User(
            email=f"user-{uuid4().hex[:8]}@example.com",
            hashed_password="hashed",
            role=UserRole.USER,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user, "fake-token"  # We'll need to mock auth


async def _create_generation_task(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    *,
    status: GenerationTaskStatus = GenerationTaskStatus.QUEUED,
) -> GenerationTask:
    """Create a generation task for testing."""
    async with session_factory() as session:
        task = GenerationTask(
            id=uuid4(),
            user_id=user_id,
            prompt="Test prompt",
            parameters={
                "width": 512,
                "height": 512,
                "inference_steps": 30,
                "guidance_scale": 7.5,
                "model": "stable-diffusion-xl",
                "scheduler": "ddim",
            },
            status=status,
            priority=5,
            subscription_tier="standard",
            s3_bucket="test-bucket",
            s3_key="test-key",
            input_url="https://example.com/input.jpg",
            metadata={},
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


@pytest.mark.asyncio()
async def test_list_generation_tasks_empty(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test listing tasks when user has none."""
    user, token = await _create_user_with_session(session_factory)

    response = await async_client.get(
        "/api/v1/generation/tasks", headers={"X-User-Id": str(user.id)}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["pagination"]["total"] == 0
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["has_next"] is False


@pytest.mark.asyncio()
async def test_list_generation_tasks_with_results(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test listing tasks returns user's tasks."""
    user, token = await _create_user_with_session(session_factory)

    # Create some tasks for this user
    task1 = await _create_generation_task(
        session_factory, user.id, status=GenerationTaskStatus.QUEUED
    )
    task2 = await _create_generation_task(
        session_factory, user.id, status=GenerationTaskStatus.COMPLETED
    )

    # Create a task for another user (should not appear)
    other_user, _ = await _create_user_with_session(session_factory)
    await _create_generation_task(session_factory, other_user.id)

    response = await async_client.get(
        "/api/v1/generation/tasks", headers={"X-User-Id": str(user.id)}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["pagination"]["total"] == 2

    # Verify the tasks belong to the correct user
    task_ids = {item["task_id"] for item in data["items"]}
    assert str(task1.id) in task_ids
    assert str(task2.id) in task_ids


@pytest.mark.asyncio()
async def test_list_generation_tasks_pagination(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test pagination works correctly."""
    user, token = await _create_user_with_session(session_factory)

    # Create 15 tasks
    for _ in range(15):
        await _create_generation_task(session_factory, user.id)

    # Get first page (10 items)
    response = await async_client.get(
        "/api/v1/generation/tasks?page=1&page_size=10",
        headers={"X-User-Id": str(user.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["pagination"]["total"] == 15
    assert data["pagination"]["has_next"] is True
    assert data["pagination"]["has_previous"] is False

    # Get second page (5 items)
    response = await async_client.get(
        "/api/v1/generation/tasks?page=2&page_size=10",
        headers={"X-User-Id": str(user.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["pagination"]["total"] == 15
    assert data["pagination"]["has_next"] is False
    assert data["pagination"]["has_previous"] is True


@pytest.mark.asyncio()
async def test_get_generation_status_success(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test getting status of a specific task."""
    user, token = await _create_user_with_session(session_factory)
    task = await _create_generation_task(
        session_factory, user.id, status=GenerationTaskStatus.PROCESSING
    )

    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/status", headers={"X-User-Id": str(user.id)}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == str(task.id)
    assert data["status"] == "processing"
    assert data["prompt"] == "Test prompt"


@pytest.mark.asyncio()
async def test_get_generation_status_not_found(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test getting status of non-existent task returns 404."""
    user, token = await _create_user_with_session(session_factory)

    fake_task_id = uuid4()
    response = await async_client.get(
        f"/api/v1/tasks/{fake_task_id}/status", headers={"X-User-Id": str(user.id)}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


@pytest.mark.asyncio()
async def test_get_generation_status_wrong_user(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test getting status of another user's task returns 404."""
    user, token = await _create_user_with_session(session_factory)
    other_user, _ = await _create_user_with_session(session_factory)

    # Create task for other user
    task = await _create_generation_task(session_factory, other_user.id)

    # Try to access other user's task
    response = await async_client.get(
        f"/api/v1/tasks/{task.id}/status", headers={"X-User-Id": str(user.id)}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


@pytest.mark.asyncio()
async def test_list_tasks_respects_page_size_limits(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that page_size parameter respects min/max constraints."""
    user, token = await _create_user_with_session(session_factory)

    # Create some tasks
    for _ in range(5):
        await _create_generation_task(session_factory, user.id)

    # Test with small page_size
    response = await async_client.get(
        "/api/v1/generation/tasks?page_size=2", headers={"X-User-Id": str(user.id)}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["pagination"]["page_size"] == 2

    # Test page number validation (must be >= 1)
    response = await async_client.get(
        "/api/v1/generation/tasks?page=0", headers={"X-User-Id": str(user.id)}
    )
    assert response.status_code == 422  # Validation error
