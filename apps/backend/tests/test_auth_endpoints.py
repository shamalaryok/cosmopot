from __future__ import annotations

from typing import Any, Mapping, cast

import pytest
from httpx import AsyncClient, Response


def _json_mapping(response: Response) -> dict[str, object]:
    payload: object = response.json()
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


async def _register(async_client: AsyncClient, email: str, password: str) -> str:
    response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    payload = _json_mapping(response)
    token_obj: object = payload.get("verification_token")
    assert isinstance(token_obj, str)
    return token_obj


async def _verify(async_client: AsyncClient, token: str) -> None:
    response = await async_client.post("/api/v1/auth/verify", json={"token": token})
    assert response.status_code == 200


async def _login(
    async_client: AsyncClient, email: str, password: str
) -> dict[str, object]:
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return _json_mapping(response)


@pytest.mark.asyncio()
async def test_register_verify_and_login_flow(async_client: AsyncClient) -> None:
    email = "user@example.com"
    password = "StrongPassw0rd!"

    token = await _register(async_client, email, password)

    # Login before verification should fail.
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 403

    await _verify(async_client, token)

    login_payload = await _login(async_client, email, password)
    user_entry = login_payload.get("user")
    assert isinstance(user_entry, Mapping)
    user_mapping = cast(Mapping[str, object], user_entry)

    user_email = user_mapping.get("email")
    assert isinstance(user_email, str)
    assert user_email == email

    access_token_obj = login_payload.get("access_token")
    refresh_token_obj = login_payload.get("refresh_token")
    assert isinstance(access_token_obj, str)
    assert isinstance(refresh_token_obj, str)

    me_response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token_obj}"},
    )
    assert me_response.status_code == 200
    me_payload = _json_mapping(me_response)
    me_email = me_payload.get("email")
    is_verified = me_payload.get("is_verified")
    assert isinstance(me_email, str)
    assert me_email == email
    assert isinstance(is_verified, bool)
    assert is_verified is True


@pytest.mark.asyncio()
async def test_refresh_rotates_tokens(async_client: AsyncClient) -> None:
    email = "rotate@example.com"
    password = "RotatePass123!"

    token = await _register(async_client, email, password)
    await _verify(async_client, token)

    login_payload = await _login(async_client, email, password)
    original_refresh = login_payload["refresh_token"]
    original_session = login_payload["session_id"]

    refresh_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["session_id"] != original_session

    # Attempting to reuse the old refresh token should now fail.
    reuse_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert reuse_response.status_code == 401

    # New access token should authorise /me
    new_access = refreshed["access_token"]
    me_response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == email


@pytest.mark.asyncio()
async def test_logout_revokes_refresh_token(async_client: AsyncClient) -> None:
    email = "logout@example.com"
    password = "LogoutPass123!"

    token = await _register(async_client, email, password)
    await _verify(async_client, token)

    login_payload = await _login(async_client, email, password)
    refresh_token = login_payload["refresh_token"]

    logout_response = await async_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_response.status_code == 200
    set_cookie_headers = logout_response.headers.get_list("set-cookie")
    assert any("Max-Age=0" in header for header in set_cookie_headers)

    reuse_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert reuse_response.status_code == 401


@pytest.mark.asyncio()
async def test_rate_limit_enforced_on_login(async_client: AsyncClient) -> None:
    email = "ratelimit@example.com"
    password = "RateLimitPass123!"

    token = await _register(async_client, email, password)
    await _verify(async_client, token)

    # Consume the allowed attempts with wrong passwords.
    for _ in range(5):
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrong"},
        )
        assert response.status_code == 401

    blocked_response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrong"},
    )
    assert blocked_response.status_code == 429
    assert "Retry-After" in blocked_response.headers
