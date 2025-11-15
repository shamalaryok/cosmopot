from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from backend.auth.exceptions import InvalidTokenError
from backend.auth.tokens import TokenService
from backend.core.config import get_settings


@pytest.mark.asyncio()
async def test_token_service_roundtrip(
    configure_settings: Iterator[None],
) -> None:
    settings = get_settings()
    service = TokenService(settings)

    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token_pair = service.create_token_pair(
        user_id=user_id, session_id=session_id, role="user"
    )

    access_payload = service.decode_access_token(token_pair.access_token)
    assert access_payload.subject == user_id
    assert access_payload.session_id == session_id
    assert access_payload.token_type == "access"

    refresh_payload = service.decode_refresh_token(token_pair.refresh_token)
    assert refresh_payload.subject == user_id
    assert refresh_payload.session_id == session_id
    assert refresh_payload.token_type == "refresh"


@pytest.mark.asyncio()
async def test_token_service_type_enforcement(
    configure_settings: Iterator[None],
) -> None:
    settings = get_settings()
    service = TokenService(settings)

    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    access_token, _ = service.create_access_token(
        user_id=user_id, session_id=session_id, role="user"
    )

    with pytest.raises(InvalidTokenError):
        service.decode_refresh_token(access_token)
