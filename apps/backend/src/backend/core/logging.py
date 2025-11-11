from __future__ import annotations

import logging
import logging.config
from contextvars import ContextVar
from threading import Lock
from typing import Any

import structlog
import structlog.contextvars
import structlog.stdlib

from backend.core.config import Settings
from backend.core.constants import REQUEST_ID_CTX_KEY, SERVICE_NAME

_LOGGING_INITIALISED = False
_LOGGING_LOCK = Lock()
_REQUEST_ID_CTX: ContextVar[str | None] = ContextVar(REQUEST_ID_CTX_KEY, default=None)


def _resolve_level(level: str) -> int:
    resolved = logging.getLevelName(level.upper())
    if isinstance(resolved, str):
        return logging.INFO
    return int(resolved)


def configure_logging(settings: Settings) -> None:
    """Configure structlog + stdlib logging exactly once per process."""

    global _LOGGING_INITIALISED
    if _LOGGING_INITIALISED:
        return

    with _LOGGING_LOCK:
        if _LOGGING_INITIALISED:
            return

        level = _resolve_level(settings.log_level)
        timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                timestamper,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        logging.config.dictConfig(
            {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "structlog": {
                        "()": structlog.stdlib.ProcessorFormatter,
                        "processors": [
                            structlog.contextvars.merge_contextvars,
                            structlog.processors.add_log_level,
                            timestamper,
                            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                            structlog.processors.JSONRenderer(),
                        ],
                    }
                },
                "handlers": {
                    "default": {
                        "class": "logging.StreamHandler",
                        "formatter": "structlog",
                        "level": level,
                    }
                },
                "loggers": {
                    "": {
                        "handlers": ["default"],
                        "level": level,
                        "propagate": True,
                    },
                    "uvicorn.error": {
                        "handlers": ["default"],
                        "level": level,
                        "propagate": False,
                    },
                    "uvicorn.access": {
                        "handlers": ["default"],
                        "level": level,
                        "propagate": False,
                    },
                },
            }
        )

        structlog.contextvars.bind_contextvars(service=SERVICE_NAME)
        _LOGGING_INITIALISED = True


def bind_context(**kwargs: Any) -> None:
    structlog.contextvars.bind_contextvars(**kwargs)


def bind_request_context(request_id: str, **kwargs: Any) -> None:
    _REQUEST_ID_CTX.set(request_id)
    bind_context(**{REQUEST_ID_CTX_KEY: request_id, **kwargs})


def clear_request_context() -> None:
    _REQUEST_ID_CTX.set(None)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=SERVICE_NAME)


def get_request_id(default: str | None = None) -> str | None:
    return _REQUEST_ID_CTX.get(default)
