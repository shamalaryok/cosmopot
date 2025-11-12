from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from user_service import repository
from user_service.enums import GenerationTaskSource, GenerationTaskStatus, PromptSource
from user_service.schemas import (
    GenerationTaskCreate,
    GenerationTaskResultUpdate,
    PromptCreate,
)

from .factories import (
    generation_task_create_factory,
    generation_task_failure_update_factory,
    generation_task_result_update_factory,
    prompt_create_factory,
    user_create_factory,
)


@pytest.mark.asyncio
async def test_prompt_versioning_and_lookup(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        prompt_v1 = await repository.create_prompt(
            session, prompt_create_factory(slug="intro")
        )
        assert prompt_v1.version == 1
        assert prompt_v1.is_active is True

        fetched = await repository.get_prompt_by_slug(session, "intro")
        assert fetched is not None
        assert fetched.id == prompt_v1.id
        assert fetched.parameters["temperature"] == pytest.approx(0.5)

        prompt_v2 = await repository.create_prompt(
            session,
            prompt_create_factory(
                slug="intro",
                parameters={"temperature": 0.7, "style": "vibrant"},
            ),
        )

        await session.refresh(prompt_v1)

        assert prompt_v2.version == 2
        assert prompt_v2.is_active is True
        assert prompt_v1.is_active is False

        latest = await repository.get_prompt_by_slug(session, "intro")
        assert latest is not None
        assert latest.id == prompt_v2.id

        archived = await repository.get_prompt_by_slug(
            session, "intro", version=1, active_only=False
        )
        assert archived is not None
        assert archived.id == prompt_v1.id


@pytest.mark.asyncio
async def test_generation_task_lifecycle_transitions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await repository.create_user(session, user_create_factory())
        prompt = await repository.create_prompt(session, prompt_create_factory())

        task = await repository.create_generation_task(
            session,
            generation_task_create_factory(user_id=user.id, prompt_id=prompt.id),
        )
        assert task.status == GenerationTaskStatus.PENDING
        assert task.parameters["size"] == "1024x1024"
        assert task.queued_at is None

        queued = await repository.mark_generation_task_queued(session, task)
        assert queued.status == GenerationTaskStatus.QUEUED
        assert queued.queued_at is not None

        started = await repository.mark_generation_task_started(session, queued)
        assert started.status == GenerationTaskStatus.RUNNING
        assert started.started_at is not None

        result_update = generation_task_result_update_factory(
            result_parameters={"frames": 24}
        )
        completed = await repository.mark_generation_task_succeeded(
            session, started, result_update
        )
        assert completed.status == GenerationTaskStatus.SUCCEEDED
        assert completed.completed_at is not None
        assert completed.result_asset_url == result_update.result_asset_url
        assert completed.result_parameters["frames"] == 24
        assert completed.error is None

        fetched = await repository.get_generation_task_by_id(session, completed.id)
        assert fetched is not None
        assert fetched.status == GenerationTaskStatus.SUCCEEDED
        assert fetched.result_asset_url == result_update.result_asset_url


@pytest.mark.asyncio
async def test_generation_task_failure_records_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await repository.create_user(session, user_create_factory())
        prompt = await repository.create_prompt(session, prompt_create_factory())
        task = await repository.create_generation_task(
            session,
            generation_task_create_factory(user_id=user.id, prompt_id=prompt.id),
        )

        running = await repository.mark_generation_task_started(session, task)
        failure = generation_task_failure_update_factory(
            error="timeout", result_parameters={"attempt": 2}
        )
        failed = await repository.mark_generation_task_failed(session, running, failure)

        assert failed.status == GenerationTaskStatus.FAILED
        assert failed.error == "timeout"
        assert failed.completed_at is not None
        assert failed.result_asset_url == failure.result_asset_url
        assert failed.result_parameters["attempt"] == 2

        with pytest.raises(ValueError):
            await repository.mark_generation_task_queued(session, failed)


def test_schema_validates_s3_urls() -> None:
    with pytest.raises(ValidationError):
        PromptCreate(
            slug="invalid",
            name="Invalid",
            description="Bad preview",
            source=PromptSource.SYSTEM,
            parameters={"tone": "serious"},
            preview_asset_url="https://example.com/asset.png",
        )

    with pytest.raises(ValidationError):
        GenerationTaskResultUpdate(result_asset_url="https://example.com/asset.png")

    with pytest.raises(ValidationError):
        GenerationTaskCreate(
            user_id=1,
            prompt_id=1,
            source=GenerationTaskSource.API,
            input_asset_url="https://example.com/input",
        )


def test_generation_task_status_helpers() -> None:
    assert (
        GenerationTaskStatus.get_by_code("pending") == GenerationTaskStatus.PENDING
    )
    assert (
        GenerationTaskStatus.get_by_code("PENDING") == GenerationTaskStatus.PENDING
    )
    assert (
        GenerationTaskStatus.get_by_code("Pending") == GenerationTaskStatus.PENDING
    )

    assert (
        GenerationTaskStatus.get_by_code("completed")
        == GenerationTaskStatus.COMPLETED
    )
    assert (
        GenerationTaskStatus.get_by_code("COMPLETED")
        == GenerationTaskStatus.COMPLETED
    )

    assert (
        GenerationTaskStatus.get_by_code("failed") == GenerationTaskStatus.FAILED
    )
    assert (
        GenerationTaskStatus.get_by_code("canceled") == GenerationTaskStatus.CANCELED
    )
    assert (
        GenerationTaskStatus.get_by_code("queued") == GenerationTaskStatus.QUEUED
    )
    assert (
        GenerationTaskStatus.get_by_code("running") == GenerationTaskStatus.RUNNING
    )


def test_generation_task_status_legacy_aliases() -> None:
    assert (
        GenerationTaskStatus.get_by_code("succeeded")
        == GenerationTaskStatus.COMPLETED
    )
    assert (
        GenerationTaskStatus.get_by_code("SUCCEEDED")
        == GenerationTaskStatus.COMPLETED
    )
    assert (
        GenerationTaskStatus.get_by_code("Succeeded")
        == GenerationTaskStatus.COMPLETED
    )

    assert GenerationTaskStatus("succeeded") == GenerationTaskStatus.COMPLETED


def test_generation_task_status_get_by_code_invalid() -> None:
    with pytest.raises(ValueError, match="invalid status code"):
        GenerationTaskStatus.get_by_code("invalid")

    with pytest.raises(ValueError, match="invalid status code"):
        GenerationTaskStatus.get_by_code("unknown")

    with pytest.raises(ValueError, match="code must be a string"):
        GenerationTaskStatus.get_by_code(123)  # type: ignore[arg-type]


def test_generation_task_status_get_name() -> None:
    assert GenerationTaskStatus.get_name(GenerationTaskStatus.PENDING) == "pending"
    assert GenerationTaskStatus.get_name(GenerationTaskStatus.COMPLETED) == "completed"
    assert GenerationTaskStatus.get_name(GenerationTaskStatus.SUCCEEDED) == "completed"
    assert GenerationTaskStatus.get_name(GenerationTaskStatus.FAILED) == "failed"

    assert GenerationTaskStatus.get_name("pending") == "pending"
    assert GenerationTaskStatus.get_name("PENDING") == "pending"
    assert GenerationTaskStatus.get_name("completed") == "completed"
    assert GenerationTaskStatus.get_name("succeeded") == "completed"
    assert GenerationTaskStatus.get_name("SUCCEEDED") == "completed"


def test_generation_task_status_get_name_invalid() -> None:
    with pytest.raises(ValueError, match="invalid status code"):
        GenerationTaskStatus.get_name("invalid")

    with pytest.raises(ValueError, match="status must be"):
        GenerationTaskStatus.get_name(123)  # type: ignore[arg-type]


def test_generation_task_status_succeeded_alias() -> None:
    alias = GenerationTaskStatus.SUCCEEDED
    assert alias is GenerationTaskStatus.COMPLETED
    assert alias.value == "completed"
    assert GenerationTaskStatus.COMPLETED.value == "completed"
