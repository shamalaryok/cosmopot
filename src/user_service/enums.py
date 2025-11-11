from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Roles available to a user account."""

    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"


class SubscriptionTier(StrEnum):
    """Supported billing tiers for subscriptions."""

    FREE = "free"
    STANDARD = "standard"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(StrEnum):
    """Lifecycle states for a subscription instance."""

    TRIALING = "trialing"
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"


class PaymentStatus(StrEnum):
    """Possible settlement states for a payment record."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class TransactionType(StrEnum):
    """Ledger classification for monetary transactions."""

    CHARGE = "charge"
    REFUND = "refund"
    CREDIT = "credit"


class PromptSource(StrEnum):
    """Origin for prompt templates."""

    SYSTEM = "system"
    USER = "user"
    EXTERNAL = "external"


class PromptCategory(StrEnum):
    """Supported prompt catalogue groupings."""

    GENERIC = "generic"
    LIPS = "lips"
    CHEEKS = "cheeks"
    CHIN = "chin"
    NOSE = "nose"
    HAIR_CUT = "hair_cut"
    HAIR_COLOR = "hair_color"
    PLASTIC = "plastic"


class GenerationTaskStatus(StrEnum):
    """Lifecycle states for content generation tasks."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    SUCCEEDED = COMPLETED

    _LEGACY_ALIASES: dict[str, "GenerationTaskStatus"] = {
        "succeeded": COMPLETED,
    }

    @classmethod
    def _missing_(cls, value: object) -> GenerationTaskStatus | None:
        if isinstance(value, str):
            legacy = cls._LEGACY_ALIASES.get(value.lower())
            if legacy is not None:
                return legacy
        return super()._missing_(value)


class GenerationTaskSource(StrEnum):
    """Indicates how a generation task was initiated."""

    API = "api"
    SCHEDULER = "scheduler"
    WORKFLOW = "workflow"
