from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias, TypedDict, cast
from urllib.parse import urlparse, urlunparse

import httpx
import websockets
from fastapi import status
from websockets.exceptions import ConnectionClosed, WebSocketException

try:  # websockets >= 11
    from websockets.exceptions import InvalidStatus
except ImportError:  # pragma: no cover - fallback for websockets < 11
    from websockets.exceptions import InvalidStatusCode as InvalidStatus


JSONPrimitive = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict: TypeAlias = dict[str, JSONValue]


@dataclass(slots=True)
class AuthTokens:
    """Container for access and refresh tokens returned by the backend."""

    access_token: str
    refresh_token: str | None
    expires_in: int | None = None
    refresh_expires_in: int | None = None
    session_id: str | None = None
    user: JSONDict | None = None


class UserPayload(TypedDict, total=False):
    id: int
    email: str
    session_id: str
    account: JSONValue
    user: JSONValue


class GenerationTaskPayload(TypedDict, total=False):
    id: str
    task_id: str
    status: str


class PaginationPayload(TypedDict, total=False):
    page: int
    page_size: int
    total: int
    has_next: bool


class TaskListPayload(TypedDict, total=False):
    items: list[JSONValue]
    pagination: PaginationPayload


class PaymentPayload(TypedDict, total=False):
    confirmation_url: str


class BackendError(Exception):
    """Raised when the backend returns an unexpected response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class UnauthorizedError(BackendError):
    """Raised when the backend indicates the user is not authenticated."""


class BackendGateway:
    """Typed wrapper around the backend HTTP and WebSocket APIs."""

    def __init__(
        self,
        *,
        base_url: str,
        websocket_base_url: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._ws_base_url = (
            self._normalise_ws_base(websocket_base_url)
            if websocket_base_url
            else self._infer_ws_base(self._base_url)
        )

    @staticmethod
    def _infer_ws_base(base_url: str) -> str:
        parsed = urlparse(base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return urlunparse((scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))

    @staticmethod
    def _normalise_ws_base(base_url: str) -> str:
        parsed = urlparse(base_url)
        scheme = parsed.scheme
        if scheme not in {"ws", "wss"}:
            scheme = "wss" if scheme == "https" else "ws"
        return urlunparse((scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))

    def _ws_url(self, path: str) -> str:
        path_value = path if path.startswith("/") else f"/{path}"
        base = self._ws_base_url.rstrip("/")
        return f"{base}{path_value}"

    async def health(self) -> JSONDict:
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout
        ) as client:
            response = await client.get("/health")
        response.raise_for_status()
        return self._json_object(response)

    async def login(self, email: str, password: str) -> AuthTokens:
        payload = {"email": email, "password": password}
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout
        ) as client:
            response = await client.post("/api/v1/auth/login", json=payload)
        if response.status_code == status.HTTP_200_OK:
            data = self._json_object(response)
            user_value = data.get("user")
            user_payload: JSONDict | None = (
                cast(JSONDict, user_value) if isinstance(user_value, dict) else None
            )
            return AuthTokens(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expires_in=data.get("expires_in"),
                refresh_expires_in=data.get("refresh_expires_in"),
                session_id=(
                    str(data.get("session_id")) if data.get("session_id") else None
                ),
                user=user_payload,
            )
        self._raise_error(response)
        raise BackendError("Authentication failed")

    async def refresh(self, refresh_token: str) -> AuthTokens:
        payload = {"refresh_token": refresh_token}
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout
        ) as client:
            response = await client.post("/api/v1/auth/refresh", json=payload)
        if response.status_code == status.HTTP_200_OK:
            data = self._json_object(response)
            user_value = data.get("user")
            user_payload: JSONDict | None = (
                cast(JSONDict, user_value) if isinstance(user_value, dict) else None
            )
            return AuthTokens(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expires_in=data.get("expires_in"),
                refresh_expires_in=data.get("refresh_expires_in"),
                session_id=(
                    str(data.get("session_id")) if data.get("session_id") else None
                ),
                user=user_payload,
            )
        self._raise_error(response)
        raise UnauthorizedError(
            "Token refresh failed", status_code=response.status_code
        )

    async def logout(self, refresh_token: str | None) -> None:
        payload: dict[str, Any] = {}
        if refresh_token:
            payload["refresh_token"] = refresh_token
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout
        ) as client:
            response = await client.post("/api/v1/auth/logout", json=payload)
        if response.status_code not in {
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_204_NO_CONTENT,
        }:
            self._raise_error(response)

    async def get_current_user(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
    ) -> tuple[UserPayload, AuthTokens | None]:
        response, tokens = await self._authorized_request(
            access_token=access_token,
            refresh_token=refresh_token,
            method="GET",
            path="/api/v1/users/me",
        )
        if response.status_code == status.HTTP_200_OK:
            return cast(UserPayload, self._json_object(response)), tokens
        self._raise_error(response)
        raise BackendError("Unable to retrieve current user")

    async def update_profile(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        payload: Mapping[str, JSONValue],
    ) -> tuple[UserPayload, AuthTokens | None]:
        response, tokens = await self._authorized_request(
            access_token=access_token,
            refresh_token=refresh_token,
            method="PATCH",
            path="/api/v1/users/me/profile",
            json=payload,
        )
        if response.status_code == status.HTTP_200_OK:
            return cast(UserPayload, self._json_object(response)), tokens
        self._raise_error(response)
        raise BackendError("Profile update failed")

    async def create_generation(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        prompt: str,
        parameters: Mapping[str, JSONValue],
        upload: tuple[str, bytes, str],
    ) -> tuple[GenerationTaskPayload, AuthTokens | None]:
        data = {"prompt": prompt, "parameters": json.dumps(parameters)}
        files: dict[str, tuple[str, bytes, str]] = {"file": upload}
        response, tokens = await self._authorized_request(
            access_token=access_token,
            refresh_token=refresh_token,
            method="POST",
            path="/api/v1/generate",
            data=data,
            files=files,
        )
        if response.status_code == status.HTTP_202_ACCEPTED:
            return cast(GenerationTaskPayload, self._json_object(response)), tokens
        self._raise_error(response)
        raise BackendError("Generation request failed")

    async def list_tasks(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        page: int,
        page_size: int,
    ) -> tuple[TaskListPayload, AuthTokens | None]:
        params = {"page": page, "page_size": page_size}
        response, tokens = await self._authorized_request(
            access_token=access_token,
            refresh_token=refresh_token,
            method="GET",
            path="/api/v1/generation/tasks",
            params=params,
        )
        if response.status_code == status.HTTP_200_OK:
            return cast(TaskListPayload, self._json_object(response)), tokens
        self._raise_error(response)
        raise BackendError("Unable to load task history")

    async def create_payment(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        payload: Mapping[str, JSONValue],
    ) -> tuple[PaymentPayload, AuthTokens | None]:
        response, tokens = await self._authorized_request(
            access_token=access_token,
            refresh_token=refresh_token,
            method="POST",
            path="/api/v1/payments/create",
            json=payload,
        )
        if response.status_code == status.HTTP_201_CREATED:
            return cast(PaymentPayload, self._json_object(response)), tokens
        self._raise_error(response)
        raise BackendError("Unable to create payment")

    async def stream_task_updates(
        self,
        *,
        user_id: int,
        task_id: str,
        access_token: str,
    ) -> AsyncGenerator[str, None]:
        headers: list[tuple[str, str]] = [("X-User-Id", str(user_id))]
        if access_token:
            headers.append(("Authorization", f"Bearer {access_token}"))
        url = self._ws_url(f"/ws/tasks/{task_id}")
        try:
            async with websockets.connect(
                url,
                extra_headers=headers,
                open_timeout=self._timeout,
                close_timeout=self._timeout,
            ) as connection:
                async for message in connection:
                    if isinstance(message, bytes):
                        yield message.decode("utf-8", errors="replace")
                    else:
                        yield str(message)
        except InvalidStatus as exc:
            status_code = getattr(exc, "status_code", None)
            raise UnauthorizedError(
                "WebSocket authentication failed", status_code=status_code
            ) from exc
        except ConnectionClosed as exc:
            code = getattr(exc, "code", "unknown")
            raise BackendError(
                f"Task stream closed unexpectedly (code {code})",
                status_code=getattr(exc, "code", None),
            ) from exc
        except WebSocketException as exc:  # pragma: no cover - defensive
            raise BackendError(f"Task stream error: {exc}") from exc

    async def _authorized_request(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> tuple[httpx.Response, AuthTokens | None]:
        headers_param = kwargs.pop("headers", None)
        headers: dict[str, str] = {}
        if headers_param is not None:
            if isinstance(headers_param, Mapping):
                headers = {
                    str(key): str(value)
                    for key, value in headers_param.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
            else:
                raise TypeError("headers must be a mapping of strings")
        headers.setdefault("Authorization", f"Bearer {access_token}")

        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout
        ) as client:
            response = await client.request(method, path, headers=headers, **kwargs)
            if (
                response.status_code != status.HTTP_401_UNAUTHORIZED
                or not refresh_token
            ):
                return response, None

            tokens = await self.refresh(refresh_token)
            headers["Authorization"] = f"Bearer {tokens.access_token}"
            retry = await client.request(method, path, headers=headers, **kwargs)
            return retry, tokens

    @staticmethod
    def _json_object(response: httpx.Response) -> JSONDict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BackendError(
                "Invalid JSON payload", status_code=response.status_code
            ) from exc
        if not isinstance(payload, dict):
            raise BackendError(
                "Unexpected JSON payload", status_code=response.status_code
            )
        return cast(JSONDict, payload)

    @staticmethod
    def _raise_error(response: httpx.Response) -> None:
        message: str
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = str(
                    payload.get("detail") or payload.get("message") or payload
                )
            else:
                message = str(payload)
        except ValueError:
            message = response.text or "Unexpected backend response"

        if response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }:
            raise UnauthorizedError(message, status_code=response.status_code)
        raise BackendError(message, status_code=response.status_code)
