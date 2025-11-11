from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from bot.config import BackendConfig
from bot.exceptions import BackendError, GenerationError
from bot.models import (
    GenerationJob,
    GenerationRequest,
    GenerationResult,
    GenerationUpdate,
    UserProfile,
)
from bot.services import BackendClient, GenerationService


class _WebSocketStub:
    def __init__(self, messages: Iterable[str]) -> None:
        self._messages = list(messages)

    async def __aenter__(self) -> _WebSocketStub:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> bool:
        return False

    def __aiter__(self) -> _WebSocketStub:
        return self

    async def __anext__(self) -> str:
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)


def _response(status: int, json_payload: Any) -> httpx.Response:
    return httpx.Response(
        status,
        json=json_payload,
        request=httpx.Request("GET", "https://api.example.test/resource"),
    )


@pytest.mark.asyncio
async def test_backend_client_fetches_profile() -> None:
    http_client = AsyncMock()
    http_client.request.return_value = _response(
        200,
        {"id": 7, "username": "demo", "credits": 5},
    )
    config = BackendConfig(
        base_url="https://api.example.test", ws_url="wss://ws.example.test"
    )
    client = BackendClient(config, http_client=http_client, ws_connector=Mock())

    profile = await client.get_profile(7)

    assert isinstance(profile, UserProfile)
    assert profile.username == "demo"
    http_client.request.assert_awaited_once_with("GET", "/users/7/profile", json=None)


@pytest.mark.asyncio
async def test_backend_client_raises_backend_error_on_failure() -> None:
    http_client = AsyncMock()
    http_client.request.return_value = _response(404, {"detail": "Missing"})
    config = BackendConfig(
        base_url="https://api.example.test", ws_url="wss://ws.example.test"
    )
    client = BackendClient(config, http_client=http_client, ws_connector=Mock())

    with pytest.raises(BackendError) as exc:
        await client.get_history(1)
    assert "Missing" in str(exc.value)


@pytest.mark.asyncio
async def test_backend_client_streams_generation_updates() -> None:
    messages = [
        json.dumps({"status": "queued"}),
        json.dumps(
            {
                "status": "completed",
                "progress": 100,
                "result": {
                    "job_id": "job-1",
                    "image_url": "https://cdn/result.png",
                    "description": "done",
                    "metadata": {},
                },
            }
        ),
    ]
    http_client = AsyncMock()
    http_client.request.return_value = _response(200, {"job_id": "job-1"})
    ws_stub = _WebSocketStub(messages)

    def ws_factory(url: str) -> _WebSocketStub:
        assert url.endswith("/generations/job-1")
        return ws_stub

    config = BackendConfig(
        base_url="https://api.example.test", ws_url="wss://ws.example.test"
    )
    client = BackendClient(config, http_client=http_client, ws_connector=ws_factory)

    updates = [update async for update in client.iterate_generation_updates("job-1")]

    assert [update.status for update in updates] == ["queued", "completed"]
    assert updates[-1].result is not None


@dataclass
class _ServiceBackendStub:
    job: GenerationJob
    updates: list[GenerationUpdate]
    start_generation: AsyncMock | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.start_generation = AsyncMock()
        self.start_generation.return_value = self.job

    async def iterate_generation_updates(
        self, job_id: str
    ) -> AsyncGenerator[GenerationUpdate, None]:
        assert job_id == self.job.job_id
        for update in self.updates:
            yield update


@pytest.mark.asyncio
async def test_generation_service_executes_successfully() -> None:
    stub = _ServiceBackendStub(
        job=GenerationJob(job_id="job-123"),
        updates=[
            GenerationUpdate(status="queued", progress=None),
            GenerationUpdate(
                status="completed",
                progress=100,
                result=GenerationResult(
                    job_id="job-123",
                    image_url="https://cdn/result.png",
                    description="Finished",
                    metadata={"quality": "balanced"},
                ),
            ),
        ],
    )
    service = GenerationService(cast(BackendClient, stub))
    request = GenerationRequest(
        category="Portrait",
        prompt="Test",
        parameters={"quality": "balanced"},
        source_file_id="file-1",
    )

    statuses: list[str] = []

    async def progress(update: GenerationUpdate) -> None:
        statuses.append(update.status)

    result = await service.execute_generation(1, request, progress_callback=progress)

    assert result.image_url == "https://cdn/result.png"
    assert statuses == ["queued", "completed"]
    assert stub.start_generation is not None
    stub.start_generation.assert_awaited_once()


@pytest.mark.asyncio
async def test_generation_service_raises_on_failed_update() -> None:
    stub = _ServiceBackendStub(
        job=GenerationJob(job_id="job-123"),
        updates=[
            GenerationUpdate(status="failed", progress=None, message="No credits")
        ],
    )
    service = GenerationService(cast(BackendClient, stub))
    request = GenerationRequest(
        category="Portrait",
        prompt="Test",
        parameters={},
        source_file_id="file-1",
    )

    with pytest.raises(GenerationError) as exc:
        await service.execute_generation(1, request)
    assert "No credits" in str(exc.value)


@pytest.mark.asyncio
async def test_generation_service_wraps_backend_errors() -> None:
    stub = _ServiceBackendStub(
        job=GenerationJob(job_id="job-123"),
        updates=[GenerationUpdate(status="completed", progress=100)],
    )
    assert stub.start_generation is not None
    stub.start_generation.side_effect = BackendError("Backend unavailable")
    service = GenerationService(cast(BackendClient, stub))
    request = GenerationRequest(
        category="Portrait",
        prompt="Test",
        parameters={},
        source_file_id="file-1",
    )

    with pytest.raises(GenerationError) as exc:
        await service.execute_generation(1, request)
    assert "Backend unavailable" in str(exc.value)
