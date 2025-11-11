from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a raw password using Argon2."""

    return _hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Return ``True`` if the provided password matches the hash."""

    try:
        return _hasher.verify(hashed_password, password)
    except (VerifyMismatchError, InvalidHash):
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Determine if the stored hash no longer meets the configured parameters."""

    try:
        return _hasher.check_needs_rehash(hashed_password)
    except InvalidHash:
        return True
