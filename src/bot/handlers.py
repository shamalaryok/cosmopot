"""Aiogram handlers for bot commands and the generation FSM."""

from __future__ import annotations

from typing import Any, TypedDict, cast

from aiogram import Bot, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .callbacks import (
    CategoryCallback,
    ConfirmationCallback,
    ParameterCallback,
    PromptCallback,
)
from .constants import DEFAULT_CATEGORIES, PARAMETER_PRESETS, PROMPTS_BY_CATEGORY
from .exceptions import BackendError, GenerationError, InvalidFileError
from .fsm import GenerationStates
from .keyboards import (
    category_keyboard,
    confirmation_keyboard,
    main_menu_keyboard,
    parameter_keyboard,
    prompt_keyboard,
)
from .models import GenerationRequest, GenerationUpdate, format_history
from .services import BackendClient, GenerationService
from .validators import validate_image


class GenerationStateData(TypedDict, total=False):
    """Type definition for FSM state data during generation flow."""

    photo_file_id: str
    photo_file_name: str | None
    photo_file_size: int | None
    category: str
    prompt: str
    parameter_key: str
    parameters: dict[str, Any]
    parameter_label: str


def _extract_user_id(entity: Message | CallbackQuery) -> int | None:
    """Extract user ID from either a Message or CallbackQuery entity."""
    if isinstance(entity, Message):
        user = entity.from_user
    elif isinstance(entity, CallbackQuery):
        user = entity.from_user
    else:
        return None
    return user.id if user else None


def _get_callback_message(callback: CallbackQuery) -> Message | None:
    """Return the message associated with a callback query if available."""
    message = callback.message
    if message is None:
        return None
    if not isinstance(message, Message):
        return None
    return message


async def _get_generation_state_data(state: FSMContext) -> GenerationStateData:
    """Fetch FSM state data as a typed dictionary."""
    data = await state.get_data()
    return cast(GenerationStateData, data)


class CoreCommandHandlers:
    """Handlers for simple commands that call REST APIs."""

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    def register(self, router: Router) -> None:
        router.message.register(self.start, Command("start"))
        router.message.register(self.menu, Command("menu"))
        router.message.register(self.profile, Command("profile"))
        router.message.register(self.subscribe, Command("subscribe"))
        router.message.register(self.history, Command("history"))
        router.message.register(self.balance, Command("balance"))
        router.message.register(self.help, Command("help"))

    async def start(self, message: Message, bot: Bot) -> None:
        await message.answer(
            "👋 Welcome! I'm here to help you orchestrate AI image generations."
        )
        await message.answer(
            "Use the menu below or type a command to get started.",
            reply_markup=main_menu_keyboard(),
        )
        # Ensure commands are visible even if the bot restarts mid-chat.
        from .commands import setup_bot_commands  # Local import to avoid cycles

        await setup_bot_commands(bot)

    async def menu(self, message: Message) -> None:
        await message.answer(
            "Here are the available actions:", reply_markup=main_menu_keyboard()
        )

    async def profile(self, message: Message) -> None:
        user_id = _extract_user_id(message)
        if user_id is None:
            await message.answer("Unable to determine your Telegram ID.")
            return
        try:
            profile = await self._backend.get_profile(user_id)
        except BackendError as exc:
            await message.answer(f"⚠️ Failed to load profile: {exc}")
            return
        await message.answer(profile.to_message(), parse_mode="HTML")

    async def history(self, message: Message) -> None:
        user_id = _extract_user_id(message)
        if user_id is None:
            await message.answer("Unable to determine your Telegram ID.")
            return
        try:
            history = await self._backend.get_history(user_id)
        except BackendError as exc:
            await message.answer(f"⚠️ Failed to load history: {exc}")
            return
        await message.answer(format_history(history), parse_mode="HTML")

    async def balance(self, message: Message) -> None:
        user_id = _extract_user_id(message)
        if user_id is None:
            await message.answer("Unable to determine your Telegram ID.")
            return
        try:
            balance = await self._backend.get_balance(user_id)
        except BackendError as exc:
            await message.answer(f"⚠️ Failed to load balance: {exc}")
            return
        await message.answer(balance.to_message(), parse_mode="HTML")

    async def subscribe(self, message: Message) -> None:
        user_id = _extract_user_id(message)
        if user_id is None:
            await message.answer("Unable to determine your Telegram ID.")
            return
        try:
            status = await self._backend.subscribe(user_id)
        except BackendError as exc:
            await message.answer(f"⚠️ Subscription failed: {exc}")
            return
        await message.answer(status.to_message(), parse_mode="HTML")

    async def help(self, message: Message) -> None:
        help_text = (
            "ℹ️ <b>How to use the bot</b>\n"
            "• /profile – View your account details\n"
            "• /generate – Launch the guided generation wizard\n"
            "• /history – Review recent generations\n"
            "• /balance – Check remaining credits\n"
            "• /subscribe – Manage your subscription plan\n"
            "Need assistance? Reply in this chat and our team will follow up."
        )
        await message.answer(help_text, parse_mode="HTML")


class GenerationHandlers:
    """FSM handlers for the multi-step generation flow."""

    def __init__(
        self, backend: BackendClient, generation_service: GenerationService
    ) -> None:
        self._backend = backend
        self._service = generation_service

    def register(self, router: Router) -> None:
        router.message.register(self.cmd_generate, Command("generate"))
        router.message.register(
            self.on_photo,
            StateFilter(GenerationStates.waiting_for_photo),
        )
        router.callback_query.register(
            self.on_category_selected,
            CategoryCallback.filter(),
            StateFilter(GenerationStates.waiting_for_category),
        )
        router.callback_query.register(
            self.on_prompt_selected,
            PromptCallback.filter(),
            StateFilter(GenerationStates.waiting_for_prompt),
        )
        router.callback_query.register(
            self.on_parameter_selected,
            ParameterCallback.filter(),
            StateFilter(GenerationStates.waiting_for_parameters),
        )
        router.callback_query.register(
            self.on_confirmation,
            ConfirmationCallback.filter(),
            StateFilter(GenerationStates.waiting_for_confirmation),
        )

    async def cmd_generate(self, message: Message, state: FSMContext) -> None:
        await state.set_state(GenerationStates.waiting_for_photo)
        await message.answer(
            "📤 Please upload a reference image (JPEG/PNG, up to 10 MB)."
        )

    async def on_photo(self, message: Message, state: FSMContext) -> None:
        file_name: str | None = None
        file_id: str | None = None
        mime_type: str | None = None
        file_size: int | None = None

        if message.document is not None:
            document = message.document
            file_name = document.file_name
            file_id = document.file_id
            mime_type = document.mime_type
            file_size = document.file_size
        elif message.photo:
            photo = message.photo[-1]
            file_id = photo.file_id
            file_size = photo.file_size
            mime_type = "image/jpeg"
        else:
            await message.answer("Please send a JPEG or PNG image to continue.")
            return

        if not file_id:
            await message.answer("Unable to read the uploaded file. Please try again.")
            return

        try:
            validate_image(
                file_name=file_name, file_size=file_size, mime_type=mime_type
            )
        except InvalidFileError as exc:
            await message.answer(str(exc))
            return

        await state.update_data(
            photo_file_id=file_id,
            photo_file_name=file_name,
            photo_file_size=file_size,
        )
        await state.set_state(GenerationStates.waiting_for_category)
        await message.answer(
            "Great! Select a category to guide the generation.",
            reply_markup=category_keyboard(DEFAULT_CATEGORIES),
        )

    async def on_category_selected(
        self,
        callback: CallbackQuery,
        callback_data: CategoryCallback,
        state: FSMContext,
    ) -> None:
        message = _get_callback_message(callback)
        if message is None:
            await callback.answer(
                "Unable to process the selected category. Please try again.",
                show_alert=True,
            )
            return
        await callback.answer()
        category = callback_data.value
        await state.update_data(category=category)
        await state.set_state(GenerationStates.waiting_for_prompt)
        prompts = PROMPTS_BY_CATEGORY.get(
            category, ["Describe the scene you would like to create."]
        )
        await message.answer(
            f"Category <b>{category}</b> selected. Pick a prompt to continue:",
            reply_markup=prompt_keyboard(category, prompts),
            parse_mode="HTML",
        )

    async def on_prompt_selected(
        self,
        callback: CallbackQuery,
        callback_data: PromptCallback,
        state: FSMContext,
    ) -> None:
        message = _get_callback_message(callback)
        if message is None:
            await callback.answer(
                "Unable to process the selected prompt. Please try again.",
                show_alert=True,
            )
            return
        await callback.answer()
        prompt = callback_data.value
        await state.update_data(prompt=prompt)
        await state.set_state(GenerationStates.waiting_for_parameters)
        await message.answer(
            "Choose the rendering preset that best matches your needs:",
            reply_markup=parameter_keyboard(),
        )

    async def on_parameter_selected(
        self,
        callback: CallbackQuery,
        callback_data: ParameterCallback,
        state: FSMContext,
    ) -> None:
        message = _get_callback_message(callback)
        if message is None:
            await callback.answer(
                "Unable to process the selected parameters. Please try again.",
                show_alert=True,
            )
            return
        await callback.answer()
        preset_key = callback_data.value
        preset = PARAMETER_PRESETS.get(preset_key)
        if not preset:
            await message.answer("Unknown preset selected. Please try again.")
            return
        await state.update_data(
            parameter_key=preset_key,
            parameters=preset["settings"],
            parameter_label=preset.get("title", preset_key.title()),
        )
        await state.set_state(GenerationStates.waiting_for_confirmation)
        data = await _get_generation_state_data(state)
        summary = self._format_summary(data)
        await message.answer(
            summary,
            reply_markup=confirmation_keyboard(),
            parse_mode="HTML",
        )

    async def on_confirmation(
        self,
        callback: CallbackQuery,
        callback_data: ConfirmationCallback,
        state: FSMContext,
    ) -> None:
        message = _get_callback_message(callback)
        if message is None:
            await callback.answer(
                "Unable to process the confirmation. Please try again.",
                show_alert=True,
            )
            await state.clear()
            return
        await callback.answer()
        if callback_data.action == "restart":
            await state.set_state(GenerationStates.waiting_for_photo)
            await message.answer("Alright, send a new image to start over.")
            return

        data = await _get_generation_state_data(state)
        user_id = _extract_user_id(callback)
        if user_id is None:
            await message.answer("Unable to determine your Telegram ID.")
            await state.clear()
            return

        category = data.get("category")
        prompt = data.get("prompt")
        parameters = data.get("parameters")
        photo_file_id = data.get("photo_file_id")
        if (
            category is None
            or prompt is None
            or parameters is None
            or photo_file_id is None
        ):
            await message.answer("Generation data is incomplete. Please start over.")
            await state.set_state(GenerationStates.waiting_for_photo)
            return

        request = GenerationRequest(
            category=category,
            prompt=prompt,
            parameters=dict(parameters),
            source_file_id=photo_file_id,
            source_file_name=data.get("photo_file_name"),
        )
        await state.set_state(GenerationStates.displaying_result)
        progress_message = await message.answer("🚀 Generation in progress…")

        async def _on_progress(update: GenerationUpdate) -> None:
            text = update.format_progress()
            await progress_message.edit_text(text)

        try:
            result = await self._service.execute_generation(
                user_id, request, progress_callback=_on_progress
            )
        except GenerationError as exc:
            await progress_message.edit_text(f"❌ Generation failed: {exc}")
            await state.set_state(GenerationStates.waiting_for_photo)
            return
        await progress_message.edit_text("✅ Generation complete!")
        await message.answer(result.to_message(), parse_mode="HTML")
        await state.clear()

    @staticmethod
    def _format_summary(data: GenerationStateData) -> str:
        preset_label = data.get("parameter_label") or "Custom"
        category = data.get("category") or "Unknown"
        prompt = data.get("prompt") or "No prompt selected"
        lines = ["🧾 <b>Review your configuration</b>"]
        lines.append(f"Category: {category}")
        lines.append(f"Prompt: {prompt}")
        lines.append(f"Preset: {preset_label}")
        return "\n".join(lines)


def create_bot_router(
    backend: BackendClient,
    generation_service: GenerationService,
) -> Router:
    router = Router(name="core_commands")
    core = CoreCommandHandlers(backend)
    core.register(router)
    generation_handlers = GenerationHandlers(backend, generation_service)
    generation_handlers.register(router)
    return router
