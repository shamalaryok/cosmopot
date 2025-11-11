from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import exceptions as jsonschema_exceptions
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from .enums import (
    GenerationTaskSource,
    GenerationTaskStatus,
    PaymentStatus,
    PromptCategory,
    PromptSource,
    SubscriptionStatus,
    SubscriptionTier,
    TransactionType,
    UserRole,
)


def _quantize_two_places(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    raise ValueError("value must be a mapping")


def _coerce_optional_mapping(value: Any) -> dict[str, Any | None] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    raise ValueError("value must be a mapping")


def _validate_s3_uri(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("S3 URL must be a string")
    if not value.startswith("s3://"):
        raise ValueError("URL must use the s3:// scheme")
    if len(value) <= 5:
        raise ValueError("S3 URL must include a bucket and key")
    return value


_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


def _normalise_slug(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("slug must be a string")
    slug = value.strip().lower()
    if not slug:
        raise ValueError("slug must not be empty")
    if not _SLUG_PATTERN.fullmatch(slug):
        raise ValueError(
            "slug may contain lowercase letters, numbers, hyphens, or underscores only"
        )
    return slug


def _ensure_json_schema(value: Any) -> dict[str, Any]:
    schema = _coerce_mapping(value)
    try:
        Draft202012Validator.check_schema(schema)
    except jsonschema_exceptions.SchemaError as exc:  # pragma: no cover - defensive
        raise ValueError(
            f"parameters_schema is not a valid JSON Schema: {exc.message}"
        ) from exc
    return schema


def _validate_against_schema(
    parameters: dict[str, Any], schema: dict[str, Any]
) -> dict[str, Any]:
    validator = Draft202012Validator(schema)
    error = next(validator.iter_errors(parameters), None)
    if error is not None:
        raise ValueError(f"parameters do not conform to schema: {error.message}")
    return parameters


class UserCreate(BaseModel):
    email: EmailStr
    hashed_password: str = Field(..., min_length=8, max_length=255)
    role: UserRole = UserRole.USER
    balance: Decimal = Decimal("0.00")
    subscription_id: int | None = None
    is_active: bool = True

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("balance", mode="before")
    @classmethod
    def validate_balance(cls, value: Decimal | str | int | float) -> Decimal:
        decimal_value = Decimal(str(value))
        if decimal_value < Decimal("0"):
            raise ValueError("balance cannot be negative")
        return _quantize_two_places(decimal_value)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    hashed_password: str | None = Field(None, min_length=8, max_length=255)
    role: UserRole | None = None
    balance: Decimal | None = None
    subscription_id: int | None = None
    is_active: bool | None = None
    deleted_at: datetime | None = None

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("balance", mode="before")
    @classmethod
    def validate_balance(
        cls, value: Decimal | str | int | float | None
    ) -> Decimal | None:
        if value is None:
            return None
        return _quantize_two_places(Decimal(str(value)))


class UserRead(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    balance: Decimal
    subscription_id: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class UserProfileBase(BaseModel):
    first_name: str | None = Field(None, max_length=120)
    last_name: str | None = Field(None, max_length=120)
    telegram_id: int | None = Field(None, ge=1)
    phone_number: str | None = Field(None, max_length=40)
    country: str | None = Field(None, max_length=80)
    city: str | None = Field(None, max_length=80)


class UserProfileCreate(UserProfileBase):
    user_id: int


class UserProfileUpdate(UserProfileBase):
    pass


class UserProfileRead(UserProfileBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class UserSessionCreate(BaseModel):
    user_id: int
    session_token: str = Field(..., min_length=16, max_length=255)
    user_agent: str | None = Field(None, max_length=255)
    ip_address: str | None = Field(None, max_length=45)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def ensure_future(cls, value: datetime) -> datetime:
        candidate = value
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=UTC)
        candidate_utc = candidate.astimezone(UTC)
        if candidate_utc <= datetime.now(UTC):
            raise ValueError("expires_at must be in the future")
        return candidate_utc


class UserSessionRead(BaseModel):
    id: int
    user_id: int
    session_token: str
    user_agent: str | None
    ip_address: str | None
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None
    ended_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class UserWithProfile(UserRead):
    profile: UserProfileRead | None = None
    sessions: list[UserSessionRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SubscriptionCreate(BaseModel):
    user_id: int
    tier: SubscriptionTier
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    auto_renew: bool = True
    quota_limit: int = Field(0, ge=0)
    quota_used: int = Field(0, ge=0)
    provider_subscription_id: str | None = Field(None, max_length=120)
    provider_data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    current_period_start: datetime
    current_period_end: datetime

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("current_period_start", "current_period_end", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if isinstance(value, datetime):
            candidate = value
        else:
            candidate = datetime.fromisoformat(str(value))
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=UTC)
        return candidate.astimezone(UTC)

    @model_validator(mode="after")
    def validate_period(self) -> SubscriptionCreate:
        if self.current_period_end <= self.current_period_start:
            raise ValueError("current_period_end must be after current_period_start")
        if self.quota_used > self.quota_limit:
            raise ValueError("quota_used cannot exceed quota_limit")
        return self


class SubscriptionRenew(BaseModel):
    new_period_end: datetime
    quota_limit: int | None = Field(None, ge=0)
    provider_data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(None, max_length=255)

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("new_period_end", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if isinstance(value, datetime):
            candidate = value
        else:
            candidate = datetime.fromisoformat(str(value))
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=UTC)
        return candidate.astimezone(UTC)


class PaymentCreate(BaseModel):
    user_id: int
    subscription_id: int | None = None
    amount: Decimal
    currency: str = Field(..., min_length=3, max_length=3)
    status: PaymentStatus = PaymentStatus.COMPLETED
    provider_payment_id: str | None = Field(None, max_length=120)
    provider_data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    paid_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: Decimal | str | int | float) -> Decimal:
        decimal_value = Decimal(str(value))
        if decimal_value < Decimal("0"):
            raise ValueError("amount cannot be negative")
        return _quantize_two_places(decimal_value)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("paid_at", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value is None:
            candidate = datetime.now(UTC)
        elif isinstance(value, datetime):
            candidate = value
        else:
            candidate = datetime.fromisoformat(str(value))
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=UTC)
        return candidate.astimezone(UTC)


class TransactionCreate(BaseModel):
    subscription_id: int | None
    user_id: int
    amount: Decimal
    currency: str = Field(..., min_length=3, max_length=3)
    type: TransactionType = TransactionType.CHARGE
    description: str | None = Field(None, max_length=255)
    provider_reference: str | None = Field(None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: Decimal | str | int | float) -> Decimal:
        return _quantize_two_places(Decimal(str(value)))

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class PromptCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)
    category: PromptCategory = PromptCategory.GENERIC
    source: PromptSource = PromptSource.SYSTEM
    parameters_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "additionalProperties": True}
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    preview_asset_url: str | None = None

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        return _normalise_slug(value)

    @field_validator("parameters_schema", mode="before")
    @classmethod
    def validate_parameters_schema(cls, value: Any) -> dict[str, Any]:
        return _ensure_json_schema(value)

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_parameters(cls, value: Any) -> dict[str, Any]:
        return _coerce_mapping(value)

    @field_validator("preview_asset_url")
    @classmethod
    def validate_preview_url(cls, value: str | None) -> str | None:
        return _validate_s3_uri(value)

    @model_validator(mode="after")
    def ensure_parameters_fit_schema(self) -> PromptCreate:
        _validate_against_schema(self.parameters, self.parameters_schema)
        return self


class PromptUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)
    category: PromptCategory | None = None
    source: PromptSource | None = None
    parameters_schema: dict[str, Any] | None = None
    parameters: dict[str, Any] | None = None
    is_active: bool | None = None
    preview_asset_url: str | None = None

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("parameters_schema", mode="before")
    @classmethod
    def validate_parameters_schema(cls, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        return _ensure_json_schema(value)

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_parameters(cls, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        return _coerce_mapping(value)

    @field_validator("preview_asset_url")
    @classmethod
    def validate_preview_url(cls, value: str | None) -> str | None:
        return _validate_s3_uri(value)


class PromptRead(PromptCreate):
    id: int
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class GenerationTaskCreate(BaseModel):
    user_id: int
    prompt_id: int
    status: GenerationTaskStatus = GenerationTaskStatus.PENDING
    source: GenerationTaskSource = GenerationTaskSource.API
    parameters: dict[str, Any] = Field(default_factory=dict)
    result_parameters: dict[str, Any] = Field(default_factory=dict)
    input_asset_url: str | None = None
    result_asset_url: str | None = None

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_parameters(cls, value: Any) -> dict[str, Any]:
        return _coerce_mapping(value)

    @field_validator("result_parameters", mode="before")
    @classmethod
    def validate_result_parameters(cls, value: Any) -> dict[str, Any]:
        return _coerce_mapping(value)

    @field_validator("input_asset_url")
    @classmethod
    def validate_input_url(cls, value: str | None) -> str | None:
        return _validate_s3_uri(value)

    @field_validator("result_asset_url")
    @classmethod
    def validate_result_url(cls, value: str | None) -> str | None:
        return _validate_s3_uri(value)


class GenerationTaskRead(BaseModel):
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

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class GenerationTaskResultUpdate(BaseModel):
    result_asset_url: str | None = None
    result_parameters: dict[str, Any | None] | None = None

    @field_validator("result_asset_url")
    @classmethod
    def validate_result_url(cls, value: str | None) -> str | None:
        return _validate_s3_uri(value)

    @field_validator("result_parameters", mode="before")
    @classmethod
    def validate_result_parameters(cls, value: Any) -> dict[str, Any | None] | None:
        return _coerce_optional_mapping(value)


class GenerationTaskFailureUpdate(BaseModel):
    error: str = Field(..., min_length=1, max_length=500)
    result_asset_url: str | None = None
    result_parameters: dict[str, Any | None] | None = None

    @field_validator("result_asset_url")
    @classmethod
    def validate_result_url(cls, value: str | None) -> str | None:
        return _validate_s3_uri(value)

    @field_validator("result_parameters", mode="before")
    @classmethod
    def validate_result_parameters(cls, value: Any) -> dict[str, Any | None] | None:
        return _coerce_optional_mapping(value)
