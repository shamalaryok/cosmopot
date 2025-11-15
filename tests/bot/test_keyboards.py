from __future__ import annotations

from bot.constants import DEFAULT_CATEGORIES, PARAMETER_PRESETS, PROMPTS_BY_CATEGORY
from bot.keyboards import (
    category_keyboard,
    confirmation_keyboard,
    main_menu_keyboard,
    parameter_keyboard,
    prompt_keyboard,
)
from bot.models import GenerationResult, GenerationUpdate


def test_main_menu_keyboard_contains_core_commands() -> None:
    keyboard = main_menu_keyboard()
    texts = [button.text for row in keyboard.keyboard for button in row]
    assert "/profile" in texts
    assert "/generate" in texts


def test_category_keyboard_builds_buttons() -> None:
    markup = category_keyboard(DEFAULT_CATEGORIES)
    assert len(markup.inline_keyboard) >= 2


def test_prompt_keyboard_uses_prompts() -> None:
    category = next(iter(PROMPTS_BY_CATEGORY))
    prompts = PROMPTS_BY_CATEGORY[category]
    markup = prompt_keyboard(category, prompts)
    assert len(markup.inline_keyboard) == len(prompts)


def test_parameter_keyboard_uses_presets() -> None:
    markup = parameter_keyboard()
    assert len(markup.inline_keyboard) == len(PARAMETER_PRESETS)


def test_confirmation_keyboard_has_actions() -> None:
    markup = confirmation_keyboard()
    buttons = [button.text for row in markup.inline_keyboard for button in row]
    assert "✅ Confirm" in buttons
    assert "🔁 Start over" in buttons


def test_generation_update_formatting() -> None:
    update = GenerationUpdate(status="progress", progress=45, message="Working")
    text = update.format_progress()
    assert "45%" in text
    completed = GenerationUpdate(
        status="completed",
        progress=100,
        result=GenerationResult(job_id="job", image_url=None, description="done"),
    )
    assert completed.is_terminal()
