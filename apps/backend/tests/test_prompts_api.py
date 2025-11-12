from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies.users import get_current_user
from user_service.enums import PromptCategory, PromptSource, UserRole
from user_service.models import User
from user_service.repository import create_prompt
from user_service.schemas import PromptCreate


async def _create_admin_user(
    session_factory: async_sessionmaker[AsyncSession],
) -> User:
    """Create an admin user for testing."""
    async with session_factory() as session:
        user = User(
            email="admin@example.com",
            hashed_password="hashed",
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio()
async def test_list_prompts_returns_active_only(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await create_prompt(
            session,
            PromptCreate(
                slug="active-prompt",
                name="Active Prompt",
                description="This is active",
                category=PromptCategory.GENERIC,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={},
                is_active=True,
            ),
        )
        await create_prompt(
            session,
            PromptCreate(
                slug="inactive-prompt",
                name="Inactive Prompt",
                description="This is inactive",
                category=PromptCategory.GENERIC,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={},
                is_active=False,
            ),
        )
        await session.commit()

    response = await async_client.get("/api/v1/prompts")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["slug"] == "active-prompt"


@pytest.mark.asyncio()
async def test_list_prompts_filters_by_category(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await create_prompt(
            session,
            PromptCreate(
                slug="lips-prompt",
                name="Lips",
                description="Lips category",
                category=PromptCategory.LIPS,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={},
                is_active=True,
            ),
        )
        await create_prompt(
            session,
            PromptCreate(
                slug="cheeks-prompt",
                name="Cheeks",
                description="Cheeks category",
                category=PromptCategory.CHEEKS,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={},
                is_active=True,
            ),
        )
        await session.commit()

    response = await async_client.get("/api/v1/prompts?category=lips")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["category"] == "lips"


@pytest.mark.asyncio()
async def test_get_prompt_by_slug_success(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await create_prompt(
            session,
            PromptCreate(
                slug="test-slug",
                name="Test Prompt",
                description="Test description",
                category=PromptCategory.GENERIC,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={},
                is_active=True,
            ),
        )
        await session.commit()

    response = await async_client.get("/api/v1/prompts/test-slug")
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "test-slug"
    assert data["name"] == "Test Prompt"


@pytest.mark.asyncio()
async def test_get_prompt_by_slug_not_found(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get("/api/v1/prompts/non-existent-slug")
    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt not found"


@pytest.mark.asyncio()
async def test_get_prompt_by_slug_with_version(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        # Create version 1
        await create_prompt(
            session,
            PromptCreate(
                slug="versioned-slug",
                name="Version 1",
                description="First version",
                category=PromptCategory.GENERIC,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={"v": 1},
                is_active=True,
            ),
        )
        # Create version 2 (will deactivate version 1)
        await create_prompt(
            session,
            PromptCreate(
                slug="versioned-slug",
                name="Version 2",
                description="Second version",
                category=PromptCategory.GENERIC,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={"v": 2},
                is_active=True,
            ),
        )
        await session.commit()

    # Get version 1 specifically
    response = await async_client.get("/api/v1/prompts/versioned-slug?version=1")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == 1
    assert data["parameters"]["v"] == 1


@pytest.mark.asyncio()
async def test_get_inactive_prompt_with_include_inactive(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await create_prompt(
            session,
            PromptCreate(
                slug="inactive-test",
                name="Inactive",
                description="Inactive prompt",
                category=PromptCategory.GENERIC,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={},
                is_active=False,
            ),
        )
        await session.commit()

    # Without include_inactive flag, should fail
    response = await async_client.get("/api/v1/prompts/inactive-test")
    assert response.status_code == 404

    # With include_inactive flag, should succeed
    response = await async_client.get(
        "/api/v1/prompts/inactive-test?include_inactive=true"
    )
    assert response.status_code == 200
    assert response.json()["slug"] == "inactive-test"


@pytest.mark.asyncio()
async def test_create_prompt_requires_admin(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    app: FastAPI,
) -> None:
    # Create regular user
    async with session_factory() as session:
        user = User(
            email="user@example.com",
            hashed_password="hashed",
            role=UserRole.USER,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    # Mock the authentication to return a regular user
    async def mock_get_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        response = await async_client.post(
            "/api/v1/admin/prompts",
            json={
                "slug": "new-prompt",
                "name": "New Prompt",
                "description": "Description",
                "category": "generic",
                "source": "system",
                "parameters_schema": {"type": "object"},
                "parameters": {},
            },
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio()
async def test_create_prompt_success_as_admin(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    app: FastAPI,
) -> None:
    # Create admin user
    admin = await _create_admin_user(session_factory)

    # Mock the authentication
    async def mock_get_current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        response = await async_client.post(
            "/api/v1/admin/prompts",
            json={
                "slug": "admin-prompt",
                "name": "Admin Prompt",
                "description": "Created by admin",
                "category": "generic",
                "source": "system",
                "parameters_schema": {"type": "object"},
                "parameters": {},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["slug"] == "admin-prompt"
        assert data["version"] == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio()
async def test_update_prompt_not_found(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    app: FastAPI,
) -> None:
    admin = await _create_admin_user(session_factory)

    async def mock_get_current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        response = await async_client.patch(
            "/api/v1/admin/prompts/99999",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio()
async def test_update_prompt_success(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    app: FastAPI,
) -> None:
    # Create a prompt
    async with session_factory() as session:
        prompt = await create_prompt(
            session,
            PromptCreate(
                slug="update-test",
                name="Original Name",
                description="Original description",
                category=PromptCategory.GENERIC,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={},
                is_active=True,
            ),
        )
        await session.commit()
        prompt_id = prompt.id

    # Update as admin
    admin = await _create_admin_user(session_factory)

    async def mock_get_current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        response = await async_client.patch(
            f"/api/v1/admin/prompts/{prompt_id}",
            json={"name": "Updated Name", "description": "Updated description"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio()
async def test_update_prompt_validation_error(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    app: FastAPI,
) -> None:
    # Create a prompt with a schema
    async with session_factory() as session:
        prompt = await create_prompt(
            session,
            PromptCreate(
                slug="validation-test",
                name="Validation Test",
                description="Test",
                category=PromptCategory.GENERIC,
                source=PromptSource.SYSTEM,
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "value": {"type": "number", "minimum": 0, "maximum": 1}
                    },
                    "required": ["value"],
                    "additionalProperties": False,
                },
                parameters={"value": 0.5},
                is_active=True,
            ),
        )
        await session.commit()
        prompt_id = prompt.id

    admin = await _create_admin_user(session_factory)

    async def mock_get_current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        # Try to update with invalid parameters (out of range)
        response = await async_client.patch(
            f"/api/v1/admin/prompts/{prompt_id}",
            json={"parameters": {"value": 2.0}},
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio()
async def test_deactivate_prompt_not_found(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    app: FastAPI,
) -> None:
    admin = await _create_admin_user(session_factory)

    async def mock_get_current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        response = await async_client.delete("/api/v1/admin/prompts/99999")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio()
async def test_deactivate_prompt_success(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    app: FastAPI,
) -> None:
    # Create an active prompt
    async with session_factory() as session:
        prompt = await create_prompt(
            session,
            PromptCreate(
                slug="deactivate-test",
                name="Deactivate Test",
                description="Test",
                category=PromptCategory.GENERIC,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={},
                is_active=True,
            ),
        )
        await session.commit()
        prompt_id = prompt.id

    admin = await _create_admin_user(session_factory)

    async def mock_get_current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        # Deactivate the prompt
        response = await async_client.delete(f"/api/v1/admin/prompts/{prompt_id}")
        assert response.status_code == 204

        # Verify it's no longer in the active list
        list_response = await async_client.get("/api/v1/prompts")
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        assert all(item["slug"] != "deactivate-test" for item in items)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio()
async def test_deactivate_already_inactive_prompt(
    async_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    app: FastAPI,
) -> None:
    # Create an inactive prompt
    async with session_factory() as session:
        prompt = await create_prompt(
            session,
            PromptCreate(
                slug="already-inactive",
                name="Already Inactive",
                description="Test",
                category=PromptCategory.GENERIC,
                source=PromptSource.SYSTEM,
                parameters_schema={"type": "object"},
                parameters={},
                is_active=False,
            ),
        )
        await session.commit()
        prompt_id = prompt.id

    admin = await _create_admin_user(session_factory)

    async def mock_get_current_user() -> User:
        return admin

    app.dependency_overrides[get_current_user] = mock_get_current_user

    try:
        # Try to deactivate already inactive prompt (should succeed with no-op)
        response = await async_client.delete(f"/api/v1/admin/prompts/{prompt_id}")
        assert response.status_code == 204
    finally:
        app.dependency_overrides.pop(get_current_user, None)
