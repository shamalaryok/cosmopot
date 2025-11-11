from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from user_service import repository
from user_service.enums import PromptCategory
from user_service.models import Prompt
from user_service.schemas import PromptCreate, PromptUpdate

from .factories import prompt_create_factory


def test_prompt_create_rejects_invalid_schema() -> None:
    with pytest.raises(ValidationError):
        PromptCreate(
            slug="invalid-schema",
            name="Invalid",
            description="Bad schema",
            category=PromptCategory.LIPS,
            parameters_schema={
                "type": "object",
                "properties": {"level": {"type": "invalid"}},
            },
            parameters={"level": 1},
        )


def test_prompt_create_rejects_mismatched_parameters() -> None:
    with pytest.raises(ValidationError):
        PromptCreate(
            slug="invalid-parameters",
            name="Invalid Parameters",
            category=PromptCategory.CHEEKS,
            parameters_schema={
                "type": "object",
                "properties": {
                    "strength": {"type": "number", "minimum": 0, "maximum": 1}
                },
                "required": ["strength"],
                "additionalProperties": False,
            },
            parameters={"strength": "high"},
        )


@pytest.mark.asyncio
async def test_list_prompts_filters_by_category(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await repository.create_prompt(
            session,
            prompt_create_factory(slug="lips-soft", category=PromptCategory.LIPS),
        )
        await repository.create_prompt(
            session,
            prompt_create_factory(slug="cheeks-rose", category=PromptCategory.CHEEKS),
        )

        lips_prompts = await repository.list_prompts(
            session, category=PromptCategory.LIPS
        )
        assert len(lips_prompts) == 1
        assert lips_prompts[0].slug == "lips-soft"

        all_prompts = await repository.list_prompts(session, active_only=True)
        assert {prompt.slug for prompt in all_prompts} == {"lips-soft", "cheeks-rose"}


@pytest.mark.asyncio
async def test_update_prompt_validates_against_schema(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        prompt = await repository.create_prompt(
            session,
            prompt_create_factory(slug="schema-update"),
        )

        with pytest.raises(ValueError):
            await repository.update_prompt(
                session,
                prompt,
                PromptUpdate(parameters={"temperature": 2.0}),
            )


@pytest.mark.asyncio
async def test_update_prompt_can_reactivate_version(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        prompt_v1 = await repository.create_prompt(
            session,
            prompt_create_factory(
                slug="reactivate",
                parameters={"temperature": 0.4, "style": "soft"},
            ),
        )
        prompt_v2 = await repository.create_prompt(
            session,
            prompt_create_factory(
                slug="reactivate",
                parameters={"temperature": 0.6, "style": "bold"},
            ),
        )

        await session.refresh(prompt_v1)
        assert prompt_v1.is_active is False
        assert prompt_v2.is_active is True

        reactivated = await repository.update_prompt(
            session,
            prompt_v1,
            PromptUpdate(is_active=True),
        )

        await session.refresh(prompt_v2)

        assert reactivated.is_active is True
        assert prompt_v2.is_active is False


@pytest.mark.asyncio
async def test_create_prompt_versions_are_atomic(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    concurrency = 2
    slug = "atomic-version"
    ready = 0
    barrier = asyncio.Event()
    lock = asyncio.Lock()

    async def wait_for_start() -> None:
        nonlocal ready
        async with lock:
            ready += 1
            if ready == concurrency:
                barrier.set()
        await barrier.wait()

    async def worker() -> Prompt:
        async with session_factory() as session:
            async with session.begin():
                await wait_for_start()
                prompt = await repository.create_prompt(
                    session,
                    prompt_create_factory(slug=slug),
                )
            return prompt

    prompts = await asyncio.gather(*(worker() for _ in range(concurrency)))
    versions = sorted(prompt.version for prompt in prompts)
    assert versions == [1, 2]

    async with session_factory() as session:
        stored_prompts = await repository.list_prompts(
            session,
            active_only=False,
        )
        relevant = [prompt for prompt in stored_prompts if prompt.slug == slug]
        assert len(relevant) == concurrency
        version_state = {prompt.version: prompt.is_active for prompt in relevant}
        assert set(version_state) == {1, 2}
        assert version_state[2] is True
        assert version_state[1] is False

        latest = await repository.get_latest_prompt_by_slug(
            session,
            slug,
            active_only=False,
        )
        assert latest is not None
        assert latest.version == 2
        assert latest.is_active is True

        latest_active = await repository.get_latest_prompt_by_slug(session, slug)
        assert latest_active is not None
        assert latest_active.version == 2

        prompt_lookup = await repository.get_prompt_by_slug(session, slug)
        assert prompt_lookup is not None
        assert prompt_lookup.version == 2
