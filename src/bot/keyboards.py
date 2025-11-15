"""Keyboard builders used by the bot handlers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .callbacks import (
    CategoryCallback,
    ConfirmationCallback,
    ParameterCallback,
    PromptCallback,
)
from .constants import PARAMETER_PRESETS


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard exposing the main commands."""

    buttons = [
        [KeyboardButton(text="/menu"), KeyboardButton(text="/profile")],
        [KeyboardButton(text="/generate"), KeyboardButton(text="/history")],
        [KeyboardButton(text="/balance"), KeyboardButton(text="/subscribe")],
        [KeyboardButton(text="/help")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def category_keyboard(categories: Sequence[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(
            text=category,
            callback_data=CategoryCallback(value=category).pack(),
        )
    builder.adjust(2)
    return builder.as_markup()


def prompt_keyboard(category: str, prompts: Sequence[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for prompt in prompts:
        builder.button(
            text=prompt[:64],
            callback_data=PromptCallback(value=prompt).pack(),
        )
    builder.adjust(1)
    return builder.as_markup()


def parameter_keyboard(
    presets: Mapping[str, Mapping[str, object]] | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    data = presets or PARAMETER_PRESETS
    for key, value in data.items():
        title = str(value.get("title", key.title()))
        builder.button(
            text=title,
            callback_data=ParameterCallback(value=key).pack(),
        )
    builder.adjust(1)
    return builder.as_markup()


def confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Confirm",
        callback_data=ConfirmationCallback(action="confirm").pack(),
    )
    builder.button(
        text="🔁 Start over",
        callback_data=ConfirmationCallback(action="restart").pack(),
    )
    builder.adjust(2)
    return builder.as_markup()
