from __future__ import annotations

from typing import Any

import aiogram.fsm.storage.redis as redis_storage

__all__ = ["DefaultKeyBuilder"]

DefaultKeyBuilder: type[Any] = redis_storage.DefaultKeyBuilder
