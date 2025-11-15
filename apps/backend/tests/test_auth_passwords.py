from __future__ import annotations

from backend.auth.passwords import hash_password, needs_rehash, verify_password


def test_password_hashing_and_verification() -> None:
    raw = "correct horse battery staple"
    hashed = hash_password(raw)

    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("wrong", hashed) is False
    assert needs_rehash(hashed) is False
