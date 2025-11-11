"""Custom exceptions used across the bot package."""

from __future__ import annotations


class BotError(Exception):
    """Base error for bot-related failures."""


class BackendError(BotError):
    """Raised when the backend returns an error response."""


class GenerationError(BotError):
    """Raised when the generation workflow fails."""


class InvalidFileError(BotError):
    """Raised when the user provides an unsupported file."""
