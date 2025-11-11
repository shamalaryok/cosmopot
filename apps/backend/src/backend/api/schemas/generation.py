from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.generation.enums import GenerationTaskStatus

__all__ = [
    "GenerationParameters",
    "GenerationTaskEnvelope",
    "GenerationTaskStatusResponse",
    "PaginationMeta",
    "GenerationTaskListResponse",
]


class GenerationParameters(BaseModel):
    """Validated generation parameters accepted by the API."""

    width: int = Field(default=512, ge=64, le=2048)
    height: int = Field(default=512, ge=64, le=2048)
    inference_steps: int = Field(default=30, ge=1, le=200)
    guidance_scale: float = Field(default=7.5, ge=0.0, le=50.0)
    seed: int | None = Field(default=None, ge=0)
    model: str = Field(default="stable-diffusion-xl", min_length=3, max_length=128)
    scheduler: str = Field(default="ddim", min_length=2, max_length=64)

    model_config = ConfigDict(extra="forbid")


class GenerationTaskEnvelope(BaseModel):
    """Response payload returned when a task is accepted."""

    id: UUID = Field(serialization_alias="task_id")
    status: GenerationTaskStatus
    prompt: str
    parameters: GenerationParameters
    priority: int
    subscription_tier: str
    input_url: str | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class GenerationTaskStatusResponse(GenerationTaskEnvelope):
    """Extended payload for task status polling."""

    updated_at: datetime
    error_message: str | None = Field(default=None, serialization_alias="error")


class PaginationMeta(BaseModel):
    """Common pagination metadata returned by list endpoints."""

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    has_next: bool
    has_previous: bool


class GenerationTaskListResponse(BaseModel):
    """Paginated response containing generation tasks."""

    items: list[GenerationTaskStatusResponse]
    pagination: PaginationMeta

    model_config = ConfigDict(from_attributes=True)
