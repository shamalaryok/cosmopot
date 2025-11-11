"""Service layer that integrates with the backend REST and WebSocket APIs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any

import httpx
import websockets
from httpx import Response

from .config import BackendConfig
from .exceptions import BackendError, GenerationError
from .models import (
    Balance,
    GenerationHistoryItem,
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationUpdate,
    SubscriptionStatus,
    UserProfile,
)

ProgressCallback = Callable[[GenerationUpdate], Awaitable[None]]


class WebSocketConnector:
    """Factory that opens WebSocket connections."""

    def __init__(self, headers: Mapping[str, str] | None = None) -> None:
        self._headers = headers

    def __call__(
        self, url: str
    ) -> AbstractAsyncContextManager[Any]:  # pragma: no cover - thin wrapper
        return websockets.connect(url, extra_headers=self._headers)


class BackendClient:
    """Lightweight REST/WebSocket client used by the handlers."""

    def __init__(
        self,
        config: BackendConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
        ws_connector: Callable[[str], AbstractAsyncContextManager[Any]] | None = None,
    ) -> None:
        self._config = config
        self._http = http_client or httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            headers=config.headers,
        )
        self._ws_base = config.ws_url.rstrip("/")
        self._ws_connector = ws_connector or WebSocketConnector(config.headers)

    async def close(self) -> None:
        await self._http.aclose()

    async def get_profile(self, user_id: int) -> UserProfile:
        payload = await self._request_json("GET", f"/users/{user_id}/profile")
        return UserProfile.model_validate(payload)

    async def get_history(self, user_id: int) -> list[GenerationHistoryItem]:
        payload = await self._request_json("GET", f"/users/{user_id}/generations")
        return [GenerationHistoryItem.model_validate(item) for item in payload]

    async def get_balance(self, user_id: int) -> Balance:
        payload = await self._request_json("GET", f"/users/{user_id}/balance")
        return Balance.model_validate(payload)

    async def subscribe(self, user_id: int) -> SubscriptionStatus:
        payload = await self._request_json("POST", f"/users/{user_id}/subscribe")
        return SubscriptionStatus.model_validate(payload)

    async def start_generation(
        self, user_id: int, request: GenerationRequest
    ) -> GenerationJob:
        payload = await self._request_json(
            "POST",
            f"/users/{user_id}/generations",
            json=request.model_dump(),
        )
        return GenerationJob.model_validate(payload)

    async def iterate_generation_updates(
        self, job_id: str
    ) -> AsyncIterator[GenerationUpdate]:
        url = f"{self._ws_base}/generations/{job_id}"
        try:
            async with self._ws_connector(url) as websocket:
                async for message in websocket:
                    try:
                        payload = json.loads(message)
                    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                        raise BackendError(
                            "Received invalid JSON from the backend"
                        ) from exc
                    yield GenerationUpdate.model_validate(payload)
        except websockets.WebSocketException as exc:  # pragma: no cover - defensive
            raise BackendError("WebSocket connection failed") from exc

    async def _request_json(
        self, method: str, url: str, *, json: Any | None = None
    ) -> Any:
        response = await self._http.request(method, url, json=json)
        return self._parse_response(response)

    def _parse_response(self, response: Response) -> Any:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = self._extract_error_message(response)
            raise BackendError(detail) from exc
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text

    @staticmethod
    def _extract_error_message(response: Response) -> str:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return f"Backend responded with status {response.status_code}"
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("error")
            if isinstance(detail, str):
                return detail
        return f"Backend responded with status {response.status_code}"


class GenerationService:
    """Coordinates the generation FSM with the backend services."""

    def __init__(self, backend: BackendClient) -> None:
        self._backend = backend

    async def execute_generation(
        self,
        user_id: int,
        request: GenerationRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> GenerationResult:
        callback = progress_callback or _noop_progress_callback
        try:
            job = await self._backend.start_generation(user_id, request)
        except BackendError as exc:
            raise GenerationError(str(exc)) from exc

        result: GenerationResult | None = None
        try:
            async for update in self._backend.iterate_generation_updates(job.job_id):
                await callback(update)
                if update.status == "failed":
                    raise GenerationError(update.message or "Generation failed.")
                if update.status == "completed" and update.result:
                    result = update.result
                    break
        except BackendError as exc:
            raise GenerationError(str(exc)) from exc

        if result is None:
            raise GenerationError("Generation finished without providing a result.")
        return result


async def _noop_progress_callback(
    _: GenerationUpdate,
) -> None:  # pragma: no cover - trivial
    await asyncio.sleep(0)
