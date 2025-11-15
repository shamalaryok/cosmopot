"""Telegram bot package exposing routers and services."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from bot_runtime.runtime import BotRuntime

from .commands import BOT_COMMANDS, get_bot_commands, setup_bot_commands
from .config import BackendConfig
from .fsm import GenerationStates
from .handlers import CoreCommandHandlers, GenerationHandlers, create_bot_router
from .services import BackendClient, GenerationService

__all__ = (
    "BackendClient",
    "BackendConfig",
    "BOT_COMMANDS",
    "BotRuntime",
    "CoreCommandHandlers",
    "GenerationHandlers",
    "GenerationService",
    "GenerationStates",
    "create_bot_router",
    "get_bot_commands",
    "setup_bot_commands",
)
