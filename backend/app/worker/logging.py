from __future__ import annotations

from logging.config import dictConfig
from typing import TYPE_CHECKING

import structlog
import structlog.types
from structlog.contextvars import merge_contextvars
from structlog.stdlib import BoundLogger
from structlog.stdlib import get_logger as get_structlog_logger


def _stack_info_renderer() -> structlog.types.Processor:
    """Return StackInfoRenderer with omit_if_debug kwarg if supported."""
    if TYPE_CHECKING:
        return structlog.processors.StackInfoRenderer()

    try:
        return structlog.processors.StackInfoRenderer(omit_if_debug=True)
    except TypeError:
        return structlog.processors.StackInfoRenderer()


def configure_logging(level: str = "INFO") -> None:
    """Configure structured logging for the worker using structlog."""

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": structlog.processors.JSONRenderer(),
                }
            },
            "handlers": {
                "default": {
                    "level": level,
                    "class": "logging.StreamHandler",
                    "formatter": "structlog",
                }
            },
            "loggers": {
                "": {"handlers": ["default"], "level": level},
                "celery": {"handlers": ["default"], "level": level, "propagate": False},
            },
        }
    )

    processors: list[structlog.types.Processor] = [
        merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _stack_info_renderer(),
        structlog.processors.format_exc_info,
        structlog.processors.EventRenamer("message"),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> BoundLogger:
    """Helper returning a structured logger bound to *name*."""
    return get_structlog_logger(name)
