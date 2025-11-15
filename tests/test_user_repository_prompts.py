from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from user_service.enums import PromptCategory
from user_service.repository import (
    create_prompt,
    get_prompt_by_slug,
    list_prompts,
    update_prompt,
)
from user_service.schemas import PromptUpdate

from .factories import prompt_create_factory


@pytest.mark.asyncio
async def test_get_prompt_by_slug_when_no_active_versions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test get_prompt_by_slug returns None when no active versions exist."""
    async with session_factory() as session:
        # Create an inactive prompt
        await create_prompt(
            session,
            prompt_create_factory(slug="inactive-only", is_active=False),
        )
        await session.commit()

        # Try to get it with active_only=True (default)
        result = await get_prompt_by_slug(session, "inactive-only", active_only=True)
        assert result is None

        # Should work with active_only=False
        result = await get_prompt_by_slug(session, "inactive-only", active_only=False)
        assert result is not None
        assert result.slug == "inactive-only"


@pytest.mark.asyncio
async def test_get_prompt_by_slug_specific_version_inactive(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test get_prompt_by_slug can fetch specific inactive versions."""
    async with session_factory() as session:
        # Create version 1 (will become inactive)
        prompt_v1 = await create_prompt(
            session,
            prompt_create_factory(slug="versioned", is_active=True),
        )
        # Create version 2 (will deactivate v1)
        await create_prompt(
            session,
            prompt_create_factory(slug="versioned", is_active=True),
        )
        await session.commit()
        await session.refresh(prompt_v1)

        # Verify v1 is now inactive
        assert prompt_v1.is_active is False

        # Should be able to get v1 by version number even though inactive
        result = await get_prompt_by_slug(session, "versioned", version=1)
        assert result is not None
        assert result.version == 1
        assert result.is_active is False


@pytest.mark.asyncio
async def test_list_prompts_with_no_category_filter(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test list_prompts returns all categories when no filter is provided."""
    async with session_factory() as session:
        await create_prompt(
            session,
            prompt_create_factory(slug="prompt-1", category=PromptCategory.LIPS),
        )
        await create_prompt(
            session,
            prompt_create_factory(slug="prompt-2", category=PromptCategory.CHEEKS),
        )
        await create_prompt(
            session,
            prompt_create_factory(slug="prompt-3", category=PromptCategory.GENERIC),
        )
        await session.commit()

        # List all active prompts without category filter
        all_prompts = await list_prompts(session, active_only=True)
        assert len(all_prompts) == 3
        slugs = {p.slug for p in all_prompts}
        assert slugs == {"prompt-1", "prompt-2", "prompt-3"}


@pytest.mark.asyncio
async def test_list_prompts_includes_inactive_when_specified(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test list_prompts includes inactive prompts when active_only=False."""
    async with session_factory() as session:
        await create_prompt(
            session,
            prompt_create_factory(slug="active", is_active=True),
        )
        await create_prompt(
            session,
            prompt_create_factory(slug="inactive", is_active=False),
        )
        await session.commit()

        # With active_only=True (default)
        active_prompts = await list_prompts(session, active_only=True)
        assert len(active_prompts) == 1
        assert active_prompts[0].slug == "active"

        # With active_only=False
        all_prompts = await list_prompts(session, active_only=False)
        assert len(all_prompts) == 2
        slugs = {p.slug for p in all_prompts}
        assert slugs == {"active", "inactive"}


@pytest.mark.asyncio
async def test_update_prompt_with_no_changes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test update_prompt handles empty update gracefully."""
    async with session_factory() as session:
        prompt = await create_prompt(
            session,
            prompt_create_factory(slug="no-changes"),
        )
        original_name = prompt.name

        # Update with empty data
        updated = await update_prompt(session, prompt, PromptUpdate())
        assert updated.name == original_name
        assert updated.id == prompt.id


@pytest.mark.asyncio
async def test_update_prompt_reactivation_deactivates_others(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test that reactivating a prompt deactivates other versions."""
    async with session_factory() as session:
        # Create three versions
        prompt_v1 = await create_prompt(
            session,
            prompt_create_factory(slug="multi-version", is_active=True),
        )
        prompt_v2 = await create_prompt(
            session,
            prompt_create_factory(slug="multi-version", is_active=True),
        )
        prompt_v3 = await create_prompt(
            session,
            prompt_create_factory(slug="multi-version", is_active=True),
        )
        await session.commit()

        # At this point, only v3 should be active
        await session.refresh(prompt_v1)
        await session.refresh(prompt_v2)
        await session.refresh(prompt_v3)
        assert prompt_v1.is_active is False
        assert prompt_v2.is_active is False
        assert prompt_v3.is_active is True

        # Reactivate v1
        await update_prompt(session, prompt_v1, PromptUpdate(is_active=True))
        await session.commit()

        # Now v1 should be active and v2, v3 should be inactive
        await session.refresh(prompt_v1)
        await session.refresh(prompt_v2)
        await session.refresh(prompt_v3)
        assert prompt_v1.is_active is True
        assert prompt_v2.is_active is False
        assert prompt_v3.is_active is False


@pytest.mark.asyncio
async def test_update_prompt_set_inactive_does_not_deactivate_others(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test that setting is_active=False doesn't deactivate other versions."""
    async with session_factory() as session:
        # Create two versions
        prompt_v1 = await create_prompt(
            session,
            prompt_create_factory(slug="deactivate-test", is_active=False),
        )
        prompt_v2 = await create_prompt(
            session,
            prompt_create_factory(slug="deactivate-test", is_active=True),
        )
        await session.commit()

        # Deactivate v2 (setting to False)
        await update_prompt(session, prompt_v2, PromptUpdate(is_active=False))
        await session.commit()

        # Both should now be inactive
        await session.refresh(prompt_v1)
        await session.refresh(prompt_v2)
        assert prompt_v1.is_active is False
        assert prompt_v2.is_active is False

        # No slug should have an active version now
        active = await list_prompts(session, active_only=True)
        assert all(p.slug != "deactivate-test" for p in active)


@pytest.mark.asyncio
async def test_update_prompt_parameters_validation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test that parameter validation works on updates."""
    async with session_factory() as session:
        prompt = await create_prompt(
            session,
            prompt_create_factory(
                slug="param-validation",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "strength": {"type": "number", "minimum": 0, "maximum": 1}
                    },
                    "required": ["strength"],
                    "additionalProperties": False,
                },
                parameters={"strength": 0.5},
            ),
        )

        # Try to update with invalid parameters
        with pytest.raises(ValueError, match="parameters do not conform to schema"):
            await update_prompt(
                session,
                prompt,
                PromptUpdate(parameters={"strength": 2.0}),  # Out of range
            )


@pytest.mark.asyncio
async def test_update_prompt_schema_and_parameters_together(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test updating both schema and parameters in one update."""
    async with session_factory() as session:
        prompt = await create_prompt(
            session,
            prompt_create_factory(
                slug="schema-param-update",
                parameters_schema={
                    "type": "object",
                    "properties": {"old_param": {"type": "string"}},
                },
                parameters={"old_param": "value"},
            ),
        )

        # Update both schema and parameters
        new_schema = {
            "type": "object",
            "properties": {"new_param": {"type": "number"}},
            "required": ["new_param"],
            "additionalProperties": False,
        }
        new_parameters = {"new_param": 42}

        updated = await update_prompt(
            session,
            prompt,
            PromptUpdate(parameters_schema=new_schema, parameters=new_parameters),
        )

        assert updated.parameters_schema == new_schema
        assert updated.parameters == new_parameters


@pytest.mark.asyncio
async def test_update_prompt_various_fields(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test updating various prompt fields."""
    async with session_factory() as session:
        prompt = await create_prompt(
            session,
            prompt_create_factory(slug="field-update"),
        )

        # Update multiple fields
        updated = await update_prompt(
            session,
            prompt,
            PromptUpdate(
                name="New Name",
                description="New Description",
                category=PromptCategory.LIPS,
                preview_asset_url="s3://test-bucket/prompts/new-preview.png",
            ),
        )

        assert updated.name == "New Name"
        assert updated.description == "New Description"
        assert updated.category == PromptCategory.LIPS
        assert updated.preview_asset_url == "s3://test-bucket/prompts/new-preview.png"


@pytest.mark.asyncio
async def test_create_prompt_with_inactive_does_not_deactivate_others(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test creating an inactive prompt doesn't affect other versions."""
    async with session_factory() as session:
        # Create active version
        prompt_v1 = await create_prompt(
            session,
            prompt_create_factory(slug="inactive-create", is_active=True),
        )
        await session.commit()

        # Create inactive version
        prompt_v2 = await create_prompt(
            session,
            prompt_create_factory(slug="inactive-create", is_active=False),
        )
        await session.commit()

        # v1 should still be active
        await session.refresh(prompt_v1)
        assert prompt_v1.is_active is True
        assert prompt_v2.is_active is False


@pytest.mark.asyncio
async def test_list_prompts_with_string_category(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Test list_prompts can handle category as string."""
    async with session_factory() as session:
        await create_prompt(
            session,
            prompt_create_factory(slug="lips-cat", category=PromptCategory.LIPS),
        )
        await create_prompt(
            session,
            prompt_create_factory(slug="cheeks-cat", category=PromptCategory.CHEEKS),
        )
        await session.commit()

        # Pass category as string
        lips_prompts = await list_prompts(session, category="lips")
        assert len(lips_prompts) == 1
        assert lips_prompts[0].slug == "lips-cat"
