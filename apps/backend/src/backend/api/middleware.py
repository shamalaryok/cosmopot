from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from backend.core.constants import REQUEST_ID_HEADER
from backend.core.logging import bind_request_context, clear_request_context

Logger = structlog.BoundLogger


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request/response pair carries a correlation identifier."""

    def __init__(self, app: ASGIApp, header_name: str = REQUEST_ID_HEADER) -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(self._header_name, str(uuid.uuid4()))
        bind_request_context(request_id=request_id)
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        finally:
            clear_request_context()

        response.headers[self._header_name] = request_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit structured logs for every inbound HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._logger: Logger = structlog.get_logger("backend.request")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        client = request.client.host if request.client is not None else "unknown"
        path = request.url.path

        try:
            response = await call_next(request)
        except Exception:  # pragma: no cover - safety net
            duration = time.perf_counter() - start
            self._logger.exception(
                "request_failed",
                method=request.method,
                path=path,
                client=client,
                duration_ms=round(duration * 1000, 3),
            )
            raise

        duration = time.perf_counter() - start
        self._logger.info(
            "request_completed",
            method=request.method,
            path=path,
            client=client,
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 3),
        )

        return response
