"""Callback data factories used by inline keyboards."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class CategoryCallback(CallbackData, prefix="cat"):
    value: str


class PromptCallback(CallbackData, prefix="prompt"):
    value: str


class ParameterCallback(CallbackData, prefix="param"):
    value: str


class ConfirmationCallback(CallbackData, prefix="confirm"):
    action: str
