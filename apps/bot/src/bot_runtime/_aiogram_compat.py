from __future__ import annotations

from typing import Any, cast

__all__ = ["DefaultKeyBuilder"]

DefaultKeyBuilder: type[Any]

try:
    import aiogram.fsm.storage.redis as redis_storage
except (ImportError, AttributeError):
    DefaultKeyBuilder = cast(type[Any], None)
else:
    DefaultKeyBuilder = cast(
        type[Any],
        cast(Any, redis_storage).DefaultKeyBuilder,
    )
