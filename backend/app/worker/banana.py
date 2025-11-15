from __future__ import annotations

import base64
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from .config import WorkerSettings


class GeminiNanoError(RuntimeError):
    """Base error for Gemini Nano client failures."""


class GeminiResponseFormatError(GeminiNanoError):
    """Raised when the API response payload is malformed."""


@dataclass(slots=True)
class GeminiResult:
    image_bytes: bytes
    metadata: Mapping[str, Any]


class GeminiNanoClient:
    """Thin wrapper around the Banana API for Gemini Nano inference."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_key: str,
        timeout: float,
        max_attempts: int,
        backoff_seconds: tuple[int, ...],
    ) -> None:
        self._api_key = api_key
        self._model_key = model_key
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._backoff = backoff_seconds
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    @classmethod
    def from_settings(cls, settings: WorkerSettings) -> GeminiNanoClient:
        return cls(
            base_url=settings.banana_api_url,
            api_key=settings.banana_api_key,
            model_key=settings.banana_model_key,
            timeout=float(settings.banana_timeout_seconds),
            max_attempts=settings.banana_max_attempts,
            backoff_seconds=settings.banana_backoff_seconds,
        )

    def close(self) -> None:
        self._client.close()

    def generate(self, input_payload: Mapping[str, Any]) -> GeminiResult:
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.post(
                    "/gemini-nano",
                    json={
                        "apiKey": self._api_key,
                        "modelKey": self._model_key,
                        "input": dict(input_payload),
                    },
                )
                response.raise_for_status()
                body = response.json()
                return self._parse_response(body)
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt >= self._max_attempts:
                    break
                sleep_for = self._backoff[min(attempt - 1, len(self._backoff) - 1)]
                time.sleep(sleep_for)
            except Exception as exc:  # pragma: no cover - unexpected errors
                raise GeminiNanoError(str(exc)) from exc
        message = str(last_error) if last_error else "Gemini Nano request failed"
        raise GeminiNanoError(message)

    @staticmethod
    def _parse_response(body: Mapping[str, Any]) -> GeminiResult:
        success = bool(body.get("success"))
        if not success:
            error_message = body.get("error") or "Gemini Nano reported failure"
            raise GeminiNanoError(str(error_message))

        output = body.get("output")
        if not isinstance(output, Mapping):
            raise GeminiResponseFormatError("Missing output field in response")
        image_b64 = output.get("image_base64")
        if not isinstance(image_b64, str):
            raise GeminiResponseFormatError("Missing base64 encoded image")
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception as exc:
            raise GeminiResponseFormatError("Invalid base64 image payload") from exc
        metadata = output.get("metadata")
        if not isinstance(metadata, Mapping):
            metadata = {}
        return GeminiResult(image_bytes=image_bytes, metadata=metadata)
