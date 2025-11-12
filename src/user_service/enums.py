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

    @classmethod
    def _missing_(cls, value: object) -> GenerationTaskStatus | None:
        if isinstance(value, str):
            legacy_aliases = {"succeeded": cls.COMPLETED}
            legacy = legacy_aliases.get(value.lower())
            if legacy is not None:
                return legacy
        return None

    @classmethod
    def _get_legacy_aliases(cls) -> dict[str, GenerationTaskStatus]:
        """Return the legacy alias mapping."""
        return {"succeeded": cls.COMPLETED}

    @classmethod
    def get_by_code(cls, code: str) -> GenerationTaskStatus:
        """Look up a status by code string.

        Normalizes case and handles legacy aliases.

        Args:
            code: The status code string to look up

        Returns:
            The matching GenerationTaskStatus enum member

        Raises:
            ValueError: If the code is not a valid status
        """
        if not isinstance(code, str):
            raise ValueError(f"code must be a string, got {type(code).__name__}")

        normalized = code.strip().lower()
        if not normalized:
            raise ValueError("code must not be empty")

        # Check legacy aliases first
        legacy_aliases = cls._get_legacy_aliases()
        if normalized in legacy_aliases:
            return legacy_aliases[normalized]

        # Try direct lookup
        try:
            return cls(normalized)
        except ValueError as exc:
            valid_codes = sorted(
                {member.value for member in cls} | set(legacy_aliases.keys())
            )
            raise ValueError(
                f"invalid status code '{code}', must be one of: "
                f"{', '.join(valid_codes)}"
            ) from exc

    @classmethod
    def get_name(cls, status: GenerationTaskStatus | str) -> str:
        """Get the canonical display name for a status.

        Args:
            status: A GenerationTaskStatus enum member or status code string

        Returns:
            The canonical name of the status (the enum member's value)

        Raises:
            ValueError: If the status is not valid
        """
        if isinstance(status, cls):
            return status.value

        if isinstance(status, str):
            resolved = cls.get_by_code(status)
            return resolved.value

        raise ValueError(
            f"status must be a GenerationTaskStatus or string, "
            f"got {type(status).__name__}"
        )


class GenerationTaskSource(StrEnum):
    """Indicates how a generation task was initiated."""

    API = "api"
    SCHEDULER = "scheduler"
    WORKFLOW = "workflow"
