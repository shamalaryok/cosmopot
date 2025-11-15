"""Configuration structures for the bot."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(slots=True)
class BackendConfig:
    """Configuration required to talk to the backend services."""

    base_url: str
    ws_url: str
    timeout: float = 10.0
    headers: Mapping[str, str] | None = field(default=None)
