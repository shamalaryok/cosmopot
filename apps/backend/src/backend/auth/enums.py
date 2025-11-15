from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Roles recognised by the authentication system."""

    ADMIN = "admin"
    USER = "user"
