from __future__ import annotations

import base64
import time
from typing import Any

import httpx
import pytest

pytest.skip("Legacy worker code - skipped in new structure", allow_module_level=True)
# ruff: noqa: E402

from backend.app.worker.banana import GeminiNanoClient, GeminiResult


class _FakeResponse(httpx.Response):
    def __init__(self, data: dict[str, Any]) -> None:
        super().__init__(
            status_code=200, request=httpx.Request("POST", "https://api"), json=data
        )


def test_gemini_client_retries_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    payload = {
        "success": True,
        "output": {
            "image_base64": base64.b64encode(b"image-bytes").decode("utf-8"),
            "metadata": {"attempt": "final"},
        },
    }

    def fake_post(self: httpx.Client, url: str, json: dict[str, Any]) -> httpx.Response:
        call_index = len(calls)
        calls.append(call_index)
        if call_index < 2:
            raise httpx.TimeoutException("timeout")
        return _FakeResponse(payload)

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda value: sleeps.append(value))

    client = GeminiNanoClient(
        base_url="https://api",
        api_key="key",
        model_key="model",
        timeout=1,
        max_attempts=3,
        backoff_seconds=(2, 4, 8),
    )

    result = client.generate({"input_base64": "ignored"})

    assert calls == [0, 1, 2]
    assert sleeps == [2, 4]
    assert isinstance(result, GeminiResult)
    assert result.image_bytes == b"image-bytes"
    assert result.metadata["attempt"] == "final"
