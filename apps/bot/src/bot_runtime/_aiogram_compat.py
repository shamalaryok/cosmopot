from __future__ import annotations

import aiogram.fsm.storage.redis as redis_storage
from typing import Any

__all__ = ["DefaultKeyBuilder"]

DefaultKeyBuilder: type[Any] = getattr(redis_storage, "DefaultKeyBuilder")
