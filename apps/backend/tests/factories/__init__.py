from __future__ import annotations

from decimal import Decimal
from itertools import count
from typing import Any

from user_service.enums import (
    PromptCategory,
    PromptSource,
    UserRole,
)
from user_service.schemas import PromptCreate, UserCreate

_counter = count(1)


def user_create_factory(
    *, email: str | None = None, role: UserRole = UserRole.USER
) -> UserCreate:
    """Factory for creating UserCreate schemas."""
    index = next(_counter)
    return UserCreate(
        email=email or f"user{index}@example.com",
        hashed_password="hashed-password-value",
        role=role,
        balance=Decimal("0.00"),
        subscription_id=None,
        is_active=True,
    )


def prompt_create_factory(
    *,
    slug: str | None = None,
    source: PromptSource = PromptSource.SYSTEM,
    category: PromptCategory = PromptCategory.GENERIC,
    parameters: dict[str, Any] | None = None,
    parameters_schema: dict[str, Any] | None = None,
    is_active: bool = True,
) -> PromptCreate:
    """Factory for creating PromptCreate schemas."""
    index = next(_counter)
    schema_payload = (
        parameters_schema
        if parameters_schema is not None
        else {
            "type": "object",
            "properties": {
                "temperature": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "style": {"type": "string"},
            },
            "required": ["temperature"],
            "additionalProperties": False,
        }
    )
    parameters_payload = (
        parameters
        if parameters is not None
        else {"temperature": 0.5, "style": "natural"}
    )
    return PromptCreate(
        slug=slug or f"prompt-{index}",
        name=f"Prompt {index}",
        description="Default prompt used for tests",
        category=category,
        source=source,
        parameters_schema=schema_payload,
        parameters=parameters_payload,
        is_active=is_active,
        preview_asset_url=f"s3://prompts/{index}/preview.png",
    )
