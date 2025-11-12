from __future__ import annotations

from typing import Any, Type

import aiogram.fsm.storage.redis as redis_storage

__all__ = ["DefaultKeyBuilder"]

_DefaultKeyBuilder = getattr(redis_storage, "DefaultKeyBuilder")
DefaultKeyBuilder = _DefaultKeyBuilder  # type: Type[Any]
