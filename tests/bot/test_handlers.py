from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from bot.callbacks import (
    CategoryCallback,
    ConfirmationCallback,
    ParameterCallback,
    PromptCallback,
)
from bot.exceptions import BackendError
from bot.fsm import GenerationStates
from bot.handlers import CoreCommandHandlers, GenerationHandlers
from bot.models import (
    Balance,
    GenerationHistoryItem,
    GenerationRequest,
    GenerationResult,
    GenerationUpdate,
    SubscriptionStatus,
    UserProfile,
)
from bot.services import GenerationService


def _make_message(user_id: int = 1) -> AsyncMock:
    message = AsyncMock(spec=Message)
    message.from_user = SimpleNamespace(id=user_id)
    message.answer = AsyncMock()
    return message


def _make_callback(user_id: int = 1) -> AsyncMock:
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = SimpleNamespace(id=user_id)
    callback.answer = AsyncMock()
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    callback.message = message
    return callback


@pytest.fixture()
def fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


@pytest.mark.asyncio
async def test_start_command_sets_menu_and_commands() -> None:
    backend = AsyncMock()
    handlers = CoreCommandHandlers(backend)
    message = _make_message()
    bot = AsyncMock()

    await handlers.start(message, bot)

    assert message.answer.await_count == 2
    bot.set_my_commands.assert_awaited_once()


@pytest.mark.asyncio
async def test_profile_command_fetches_profile() -> None:
    backend = AsyncMock()
    backend.get_profile.return_value = UserProfile(id=42, username="demo", credits=5)
    handlers = CoreCommandHandlers(backend)
    message = _make_message(42)

    await handlers.profile(message)

    backend.get_profile.assert_awaited_once_with(42)
    message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_profile_command_handles_error() -> None:
    backend = AsyncMock()
    backend.get_profile.side_effect = BackendError("boom")
    handlers = CoreCommandHandlers(backend)
    message = _make_message(42)

    await handlers.profile(message)

    text = message.answer.await_args.args[0]
    assert "boom" in text


@pytest.mark.asyncio
async def test_history_command_formats_entries() -> None:
    backend = AsyncMock()
    backend.get_history.return_value = [
        GenerationHistoryItem(
            id="1",
            created_at=datetime(2023, 1, 1, 12, 0),
            status="completed",
            prompt="Prompt",
            result_url="https://cdn/image.png",
            category="Portrait",
        )
    ]
    handlers = CoreCommandHandlers(backend)
    message = _make_message(5)

    await handlers.history(message)

    backend.get_history.assert_awaited_once_with(5)
    history_message = message.answer.await_args.args[0]
    assert "Prompt" in history_message
    assert "completed" in history_message


@pytest.mark.asyncio
async def test_history_command_handles_error() -> None:
    backend = AsyncMock()
    backend.get_history.side_effect = BackendError("timeout")
    handlers = CoreCommandHandlers(backend)
    message = _make_message(5)

    await handlers.history(message)

    assert "timeout" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_balance_command_reports_balance() -> None:
    backend = AsyncMock()
    backend.get_balance.return_value = Balance(credits=9)
    handlers = CoreCommandHandlers(backend)
    message = _make_message(3)

    await handlers.balance(message)

    backend.get_balance.assert_awaited_once_with(3)
    assert "9" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_subscribe_command_returns_status() -> None:
    backend = AsyncMock()
    backend.subscribe.return_value = SubscriptionStatus(status="active", plan="Pro")
    handlers = CoreCommandHandlers(backend)
    message = _make_message(3)

    await handlers.subscribe(message)

    backend.subscribe.assert_awaited_once_with(3)
    assert "Pro" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_help_command_outputs_usage() -> None:
    backend = AsyncMock()
    handlers = CoreCommandHandlers(backend)
    message = _make_message()

    await handlers.help(message)

    assert "How to use" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_cmd_generate_sets_state(fsm_context: FSMContext) -> None:
    backend = AsyncMock()
    service = AsyncMock(spec=GenerationService)
    handlers = GenerationHandlers(backend, service)
    message = _make_message()

    await handlers.cmd_generate(message, fsm_context)

    assert await fsm_context.get_state() == GenerationStates.waiting_for_photo.state
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_photo_rejects_invalid_file(fsm_context: FSMContext) -> None:
    backend = AsyncMock()
    service = AsyncMock(spec=GenerationService)
    handlers = GenerationHandlers(backend, service)
    await fsm_context.set_state(GenerationStates.waiting_for_photo)

    message = _make_message()
    message.document = SimpleNamespace(
        file_name="file.gif",
        file_id="doc",
        file_size=1024,
        mime_type="image/gif",
    )
    message.photo = None

    await handlers.on_photo(message, fsm_context)

    assert "Unsupported" in message.answer.await_args.args[0]
    assert await fsm_context.get_state() == GenerationStates.waiting_for_photo.state


@pytest.mark.asyncio
async def test_on_photo_advances_to_category(fsm_context: FSMContext) -> None:
    backend = AsyncMock()
    service = AsyncMock(spec=GenerationService)
    handlers = GenerationHandlers(backend, service)
    await fsm_context.set_state(GenerationStates.waiting_for_photo)

    message = _make_message()
    message.document = SimpleNamespace(
        file_name="file.jpg",
        file_id="doc",
        file_size=2048,
        mime_type="image/jpeg",
    )
    message.photo = None

    await handlers.on_photo(message, fsm_context)

    assert await fsm_context.get_state() == GenerationStates.waiting_for_category.state
    data = await fsm_context.get_data()
    assert data["photo_file_id"] == "doc"


@pytest.mark.asyncio
async def test_category_selection_moves_to_prompt(fsm_context: FSMContext) -> None:
    backend = AsyncMock()
    service = AsyncMock(spec=GenerationService)
    handlers = GenerationHandlers(backend, service)
    await fsm_context.set_state(GenerationStates.waiting_for_category)

    callback = _make_callback()

    await handlers.on_category_selected(
        callback,
        CategoryCallback(value="Portrait"),
        fsm_context,
    )

    assert await fsm_context.get_state() == GenerationStates.waiting_for_prompt.state
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_prompt_selection_moves_to_parameters(fsm_context: FSMContext) -> None:
    backend = AsyncMock()
    service = AsyncMock(spec=GenerationService)
    handlers = GenerationHandlers(backend, service)
    await fsm_context.set_state(GenerationStates.waiting_for_prompt)

    callback = _make_callback()

    await handlers.on_prompt_selected(
        callback,
        PromptCallback(value="Describe"),
        fsm_context,
    )

    assert (
        await fsm_context.get_state() == GenerationStates.waiting_for_parameters.state
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_parameter_selection_prepares_confirmation(
    fsm_context: FSMContext,
) -> None:
    backend = AsyncMock()
    service = AsyncMock(spec=GenerationService)
    handlers = GenerationHandlers(backend, service)
    await fsm_context.set_state(GenerationStates.waiting_for_parameters)
    await fsm_context.update_data(category="Portrait", prompt="Prompt")

    callback = _make_callback()

    await handlers.on_parameter_selected(
        callback,
        ParameterCallback(value="balanced"),
        fsm_context,
    )

    assert (
        await fsm_context.get_state() == GenerationStates.waiting_for_confirmation.state
    )
    data = await fsm_context.get_data()
    assert data["parameters"]["quality"] == "balanced"


@pytest.mark.asyncio
async def test_parameter_selection_handles_unknown_preset(
    fsm_context: FSMContext,
) -> None:
    backend = AsyncMock()
    service = AsyncMock(spec=GenerationService)
    handlers = GenerationHandlers(backend, service)
    await fsm_context.set_state(GenerationStates.waiting_for_parameters)

    callback = _make_callback()

    await handlers.on_parameter_selected(
        callback,
        ParameterCallback(value="missing"),
        fsm_context,
    )

    callback.message.answer.assert_awaited_once()
    assert (
        await fsm_context.get_state() == GenerationStates.waiting_for_parameters.state
    )


@pytest.mark.asyncio
async def test_confirmation_restart_resets_state(fsm_context: FSMContext) -> None:
    backend = AsyncMock()
    service = AsyncMock(spec=GenerationService)
    handlers = GenerationHandlers(backend, service)
    await fsm_context.set_state(GenerationStates.waiting_for_confirmation)

    callback = _make_callback()

    await handlers.on_confirmation(
        callback,
        ConfirmationCallback(action="restart"),
        fsm_context,
    )

    assert await fsm_context.get_state() == GenerationStates.waiting_for_photo.state


@pytest.mark.asyncio
async def test_confirmation_runs_generation(fsm_context: FSMContext) -> None:
    backend = AsyncMock()

    async def execute_generation(
        user_id: int,
        request: GenerationRequest,
        progress_callback: Callable[[GenerationUpdate], Awaitable[None]] | None = None,
    ) -> GenerationResult:
        if progress_callback is not None:
            await progress_callback(
                GenerationUpdate(status="progress", progress=30, message="Working")
            )
        return GenerationResult(
            job_id="job-1",
            image_url="https://cdn/img.png",
            description="Done",
            metadata={"quality": "balanced"},
        )

    service = AsyncMock(spec=GenerationService)
    service.execute_generation.side_effect = execute_generation

    handlers = GenerationHandlers(backend, service)
    await fsm_context.set_state(GenerationStates.waiting_for_confirmation)
    await fsm_context.update_data(
        category="Portrait",
        prompt="Prompt",
        parameters={"quality": "balanced"},
        parameter_label="Balanced",
        photo_file_id="file-1",
        photo_file_name="image.png",
    )

    progress_message = AsyncMock()
    progress_message.edit_text = AsyncMock()

    final_message = AsyncMock()

    callback = _make_callback(user_id=99)
    callback.message.answer.side_effect = [progress_message, final_message]

    await handlers.on_confirmation(
        callback,
        ConfirmationCallback(action="confirm"),
        fsm_context,
    )

    assert await fsm_context.get_state() is None
    service.execute_generation.assert_awaited_once()
    calls = [args.args[0] for args in progress_message.edit_text.await_args_list]
    assert any("Progress: 30%" in text for text in calls)
    assert calls[-1] == "✅ Generation complete!"
    callback.message.answer.assert_awaited()
