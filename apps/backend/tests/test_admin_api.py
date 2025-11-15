from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TypeVar
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from user_service.enums import (
    GenerationTaskSource,
    GenerationTaskStatus,
    PromptCategory,
    PromptSource,
    SubscriptionStatus,
    SubscriptionTier,
    UserRole,
)
from user_service.models import GenerationTask, Prompt, Subscription, User

T = TypeVar("T")


async def _persist(session: AsyncSession, instance: T) -> T:
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


async def create_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    email: str | None = None,
    role: UserRole = UserRole.USER,
    is_active: bool = True,
) -> User:
    async with session_factory() as session:
        user = User(
            email=email or f"user-{uuid4().hex}@example.com",
            hashed_password="hashed-password",
            role=role,
            is_active=is_active,
            balance=Decimal("100.00"),
        )
        return await _persist(session, user)


async def create_subscription(
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    *,
    tier: SubscriptionTier = SubscriptionTier.PRO,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
) -> Subscription:
    async with session_factory() as session:
        subscription = Subscription(
            user_id=user.id,
            tier=tier,
            status=status,
            quota_limit=5000,
            quota_used=100,
            current_period_start=datetime.now(UTC),
            current_period_end=datetime.now(UTC) + timedelta(days=30),
        )
        return await _persist(session, subscription)


async def create_prompt(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    slug: str | None = None,
    name: str = "Test Prompt",
    is_active: bool = True,
) -> Prompt:
    async with session_factory() as session:
        prompt = Prompt(
            slug=slug or f"prompt-{uuid4().hex[:8]}",
            name=name,
            description="Test description",
            category=PromptCategory.GENERIC,
            source=PromptSource.SYSTEM,
            version=1,
            parameters_schema={},
            parameters={"key": "value"},
            is_active=is_active,
        )
        return await _persist(session, prompt)


async def create_generation(
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    prompt: Prompt,
    *,
    status: GenerationTaskStatus = GenerationTaskStatus.COMPLETED,
) -> GenerationTask:
    async with session_factory() as session:
        generation = GenerationTask(
            user_id=user.id,
            prompt_id=prompt.id,
            status=status,
            source=GenerationTaskSource.API,
            parameters={"steps": 50},
            result_parameters={},
        )
        return await _persist(session, generation)


@pytest.mark.asyncio
class TestAdminAnalytics:
    async def test_get_analytics_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)

        response = await async_client.get(
            "/api/v1/admin/analytics",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "active_users" in data
        assert "total_generations" in data
        assert data["total_users"] >= 1

    async def test_get_analytics_as_non_admin_forbidden(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        user = await create_user(session_factory, role=UserRole.USER)

        response = await async_client.get(
            "/api/v1/admin/analytics",
            headers={"X-User-Id": str(user.id)},
        )

        assert response.status_code == 403
        assert "Administrator role required" in response.json()["detail"]


@pytest.mark.asyncio
class TestAdminUsers:
    async def test_list_users_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        await create_user(session_factory, role=UserRole.USER)
        await create_user(session_factory, role=UserRole.USER)

        response = await async_client.get(
            "/api/v1/admin/users",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 3
        assert len(data["items"]) >= 3

    async def test_list_users_with_pagination(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        for _ in range(5):
            await create_user(session_factory)

        response = await async_client.get(
            "/api/v1/admin/users?page=1&page_size=2",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    async def test_list_users_with_search(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        await create_user(session_factory, email="searchme@example.com")

        response = await async_client.get(
            "/api/v1/admin/users?search=searchme",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any("searchme" in item["email"] for item in data["items"])

    async def test_get_user_by_id(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)

        response = await async_client.get(
            f"/api/v1/admin/users/{user.id}",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user.id
        assert data["email"] == user.email

    async def test_create_user_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)

        payload = {
            "email": "newuser@example.com",
            "password": "securepassword123",
            "role": "user",
            "is_active": True,
        }

        response = await async_client.post(
            "/api/v1/admin/users",
            json=payload,
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["role"] == "user"

    async def test_update_user_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)

        payload = {"is_active": False, "role": "admin"}

        response = await async_client.patch(
            f"/api/v1/admin/users/{user.id}",
            json=payload,
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False
        assert data["role"] == "admin"

    async def test_delete_user_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)

        response = await async_client.delete(
            f"/api/v1/admin/users/{user.id}",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 204

        get_response = await async_client.get(
            f"/api/v1/admin/users/{user.id}",
            headers={"X-User-Id": str(admin.id)},
        )
        assert get_response.status_code == 404

    async def test_user_operations_as_non_admin_forbidden(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        user = await create_user(session_factory, role=UserRole.USER)

        response = await async_client.get(
            "/api/v1/admin/users",
            headers={"X-User-Id": str(user.id)},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
class TestAdminSubscriptions:
    async def test_list_subscriptions_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)
        await create_subscription(session_factory, user)

        response = await async_client.get(
            "/api/v1/admin/subscriptions",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1

    async def test_list_subscriptions_with_filters(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)
        await create_subscription(
            session_factory, user, tier=SubscriptionTier.ENTERPRISE
        )

        response = await async_client.get(
            "/api/v1/admin/subscriptions?tier=enterprise",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(item["tier"] == "enterprise" for item in data["items"])

    async def test_get_subscription_by_id(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)
        subscription = await create_subscription(session_factory, user)

        response = await async_client.get(
            f"/api/v1/admin/subscriptions/{subscription.id}",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == subscription.id
        assert data["user_id"] == user.id

    async def test_update_subscription_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)
        subscription = await create_subscription(session_factory, user)

        payload = {"status": "canceled", "auto_renew": False}

        response = await async_client.patch(
            f"/api/v1/admin/subscriptions/{subscription.id}",
            json=payload,
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "canceled"
        assert data["auto_renew"] is False


@pytest.mark.asyncio
class TestAdminPrompts:
    async def test_list_prompts_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        await create_prompt(session_factory)

        response = await async_client.get(
            "/api/v1/admin/prompts",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1

    async def test_list_prompts_with_filters(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        await create_prompt(session_factory, name="Searchable Prompt")

        response = await async_client.get(
            "/api/v1/admin/prompts?search=Searchable",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any("Searchable" in item["name"] for item in data["items"])

    async def test_create_prompt_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)

        payload = {
            "slug": "new-prompt",
            "name": "New Prompt",
            "description": "Test prompt",
            "category": "generic",
            "source": "system",
            "version": 1,
            "parameters_schema": {},
            "parameters": {"key": "value"},
            "is_active": True,
        }

        response = await async_client.post(
            "/api/v1/admin/prompts",
            json=payload,
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "new-prompt"
        assert data["name"] == "New Prompt"

    async def test_update_prompt_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        prompt = await create_prompt(session_factory)

        payload = {"name": "Updated Prompt", "is_active": False}

        response = await async_client.patch(
            f"/api/v1/admin/prompts/{prompt.id}",
            json=payload,
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Prompt"
        assert data["is_active"] is False

    async def test_delete_prompt_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        prompt = await create_prompt(session_factory)

        response = await async_client.delete(
            f"/api/v1/admin/prompts/{prompt.id}",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 204

        get_response = await async_client.get(
            f"/api/v1/admin/prompts/{prompt.id}",
            headers={"X-User-Id": str(admin.id)},
        )
        data = get_response.json()
        assert data["is_active"] is False


@pytest.mark.asyncio
class TestAdminGenerations:
    async def test_list_generations_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)
        prompt = await create_prompt(session_factory)
        await create_generation(session_factory, user, prompt)

        response = await async_client.get(
            "/api/v1/admin/generations",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1

    async def test_list_generations_with_filters(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)
        prompt = await create_prompt(session_factory)
        await create_generation(
            session_factory, user, prompt, status=GenerationTaskStatus.FAILED
        )

        response = await async_client.get(
            "/api/v1/admin/generations?status=failed",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(item["status"] == "failed" for item in data["items"])

    async def test_get_generation_by_id(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)
        prompt = await create_prompt(session_factory)
        generation = await create_generation(session_factory, user, prompt)

        response = await async_client.get(
            f"/api/v1/admin/generations/{generation.id}",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == generation.id
        assert data["user_id"] == user.id

    async def test_update_generation_as_admin(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)
        prompt = await create_prompt(session_factory)
        generation = await create_generation(session_factory, user, prompt)

        payload = {"status": "failed", "error": "Admin marked as failed"}

        response = await async_client.patch(
            f"/api/v1/admin/generations/{generation.id}",
            json=payload,
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"] == "Admin marked as failed"

    async def test_moderate_generation_approve(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)
        prompt = await create_prompt(session_factory)
        generation = await create_generation(session_factory, user, prompt)

        payload = {"action": "approve", "reason": None}

        response = await async_client.post(
            f"/api/v1/admin/generations/{generation.id}/moderate",
            json=payload,
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    async def test_moderate_generation_reject(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)
        user = await create_user(session_factory)
        prompt = await create_prompt(session_factory)
        generation = await create_generation(session_factory, user, prompt)

        payload = {"action": "reject", "reason": "Inappropriate content"}

        response = await async_client.post(
            f"/api/v1/admin/generations/{generation.id}/moderate",
            json=payload,
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["error"] == "Inappropriate content"


@pytest.mark.asyncio
class TestAdminExports:
    async def test_export_users_csv(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)

        response = await async_client.get(
            "/api/v1/admin/users/export/csv",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]

    async def test_export_users_json(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)

        response = await async_client.get(
            "/api/v1/admin/users/export/json",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]

    async def test_export_invalid_format(
        self,
        async_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        admin = await create_user(session_factory, role=UserRole.ADMIN)

        response = await async_client.get(
            "/api/v1/admin/users/export/xml",
            headers={"X-User-Id": str(admin.id)},
        )

        assert response.status_code == 400
        assert "Invalid format" in response.json()["detail"]
