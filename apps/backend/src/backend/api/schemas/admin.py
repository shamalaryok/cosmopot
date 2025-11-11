from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from user_service.enums import (
    GenerationTaskSource,
    GenerationTaskStatus,
    PromptCategory,
    PromptSource,
    SubscriptionStatus,
    SubscriptionTier,
    UserRole,
)

__all__ = [
    "PaginatedResponse",
    "FilterParams",
    "ExportFormat",
    "AdminUserResponse",
    "AdminUserCreate",
    "AdminUserUpdate",
    "AdminSubscriptionResponse",
    "AdminSubscriptionUpdate",
    "AdminPromptResponse",
    "AdminPromptCreate",
    "AdminPromptUpdate",
    "AdminGenerationResponse",
    "AdminGenerationUpdate",
    "AdminAnalyticsResponse",
    "AdminModerationAction",
]


class FilterParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    search: str | None = None
    sort_by: str | None = None
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")

    model_config = ConfigDict(extra="forbid")


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int

    model_config = ConfigDict(extra="forbid")


class ExportFormat(BaseModel):
    format: str = Field(default="csv", pattern="^(csv|json)$")

    model_config = ConfigDict(extra="forbid")


class AdminUserResponse(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    balance: Decimal
    is_active: bool
    subscription_id: int | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=255)
    role: UserRole = Field(default=UserRole.USER)
    is_active: bool = Field(default=True)

    model_config = ConfigDict(extra="forbid")


class AdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    balance: Decimal | None = None

    model_config = ConfigDict(extra="forbid")


class AdminSubscriptionResponse(BaseModel):
    id: int
    user_id: int
    tier: SubscriptionTier
    status: SubscriptionStatus
    auto_renew: bool
    quota_limit: int
    quota_used: int
    current_period_start: datetime
    current_period_end: datetime
    canceled_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminSubscriptionUpdate(BaseModel):
    tier: SubscriptionTier | None = None
    status: SubscriptionStatus | None = None
    auto_renew: bool | None = None
    quota_limit: int | None = None
    quota_used: int | None = None

    model_config = ConfigDict(extra="forbid")


class AdminPromptResponse(BaseModel):
    id: int
    slug: str
    name: str
    description: str | None
    category: PromptCategory
    source: PromptSource
    version: int
    parameters: dict[str, Any]
    is_active: bool
    preview_asset_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminPromptCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    category: PromptCategory = Field(default=PromptCategory.GENERIC)
    source: PromptSource = Field(default=PromptSource.SYSTEM)
    version: int = Field(default=1, ge=1)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = Field(default=True)
    preview_asset_url: str | None = None

    model_config = ConfigDict(extra="forbid")


class AdminPromptUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: PromptCategory | None = None
    parameters: dict[str, Any] | None = None
    is_active: bool | None = None
    preview_asset_url: str | None = None

    model_config = ConfigDict(extra="forbid")


class AdminGenerationResponse(BaseModel):
    id: int
    user_id: int
    prompt_id: int
    status: GenerationTaskStatus
    source: GenerationTaskSource
    parameters: dict[str, Any]
    result_parameters: dict[str, Any]
    input_asset_url: str | None
    result_asset_url: str | None
    error: str | None
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminGenerationUpdate(BaseModel):
    status: GenerationTaskStatus | None = None
    error: str | None = None

    model_config = ConfigDict(extra="forbid")


class AdminModerationAction(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|flag)$")
    reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class AdminAnalyticsResponse(BaseModel):
    total_users: int
    active_users: int
    total_subscriptions: int
    active_subscriptions: int
    total_generations: int
    generations_today: int
    generations_this_week: int
    generations_this_month: int
    failed_generations: int
    revenue_total: Decimal
    revenue_this_month: Decimal

    model_config = ConfigDict(extra="forbid")
