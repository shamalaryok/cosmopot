from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from user_service.enums import PromptCategory, PromptSource


class PromptResponse(BaseModel):
    """Representation of a prompt returned by the API."""

    id: int
    slug: str
    name: str
    description: str | None
    category: PromptCategory
    source: PromptSource
    parameters_schema: dict[str, Any]
    parameters: dict[str, Any]
    version: int
    is_active: bool
    preview_asset_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class PromptListResponse(BaseModel):
    """Collection wrapper for prompt listings."""

    items: list[PromptResponse]
