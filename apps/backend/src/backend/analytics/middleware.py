"""Analytics middleware for automatic event tracking."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, cast

import structlog
from structlog.typing import FilteringBoundLogger
from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from backend.analytics.enums import AnalyticsEvent
from backend.analytics.service import AnalyticsService
from backend.core.config import Settings

logger: FilteringBoundLogger = structlog.get_logger(__name__)


class AnalyticsMiddleware(BaseHTTPMiddleware):
    """Middleware to automatically track API requests and responses."""

    def __init__(self, app: Any, analytics_service: AnalyticsService, settings: Settings) -> None:
        super().__init__(app)
        self.analytics_service = analytics_service
        self.settings = settings

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Process request and track analytics events."""
        if not self.settings.analytics.enabled:
            return await call_next(request)

        start_time = time.time()
        session_id = getattr(request.state, "session_id", str(uuid.uuid4()))
        
        # Extract user information if available
        user_id = None
        if hasattr(request.state, "user") and request.state.user:
            user_id = str(request.state.user.id)

        # Process the request
        response = await call_next(request)
        
        # Calculate processing time
        processing_time = round(
            (time.time() - start_time) * 1000, 2
        )  # in milliseconds

        # Track API call
        await self._track_api_call(
            request, response, user_id, session_id, processing_time
        )

        return response

    async def _track_api_call(
        self,
        request: Request,
        response: Response,
        user_id: str | None,
        session_id: str,
        processing_time: float,
    ) -> None:
        """Track API call analytics event."""
        try:
            # Determine event type based on endpoint and method
            event_type = self._get_event_type_from_request(request)
            if not event_type:
                return

            # Prepare event data
            event_data = {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "processing_time_ms": processing_time,
                "user_agent": request.headers.get("user-agent"),
                "ip_address": self._get_client_ip(request),
            }

            # Add query parameters (excluding sensitive ones)
            if request.query_params:
                safe_params = {
                    k: v for k, v in request.query_params.items()
                    if k.lower() not in ["token", "password", "secret", "key"]
                }
                if safe_params:
                    event_data["query_params"] = safe_params

            # Track the event asynchronously (fire and forget)
            try:
                from backend.db.dependencies import get_db_session
                
                # This is a bit of a hack since we're in middleware
                # In practice, you might want to use a background task
                session_gen = cast(AsyncGenerator[AsyncSession, None], get_db_session())
                session: AsyncSession = await anext(session_gen)
                try:
                    await self.analytics_service.track_event(
                        session=session,
                        event_type=event_type,
                        event_data=event_data,
                        user_id=user_id,
                        session_id=session_id,
                        ip_address=self._get_client_ip(request),
                        user_agent=request.headers.get("user-agent"),
                    )
                    await session.commit()
                finally:
                    await session_gen.aclose()
            except Exception as e:
                # Don't let analytics errors affect the main request
                logger.error("Failed to track analytics event", error=str(e))

        except Exception as e:
            # Don't let analytics errors affect the main request
            logger.error("Error in analytics middleware", error=str(e))

    def _get_event_type_from_request(self, request: Request) -> AnalyticsEvent | None:
        """Determine analytics event type from request path and method."""
        path = request.url.path
        method = request.method

        # Authentication events
        if path.startswith("/api/v1/auth/register") and method == "POST":
            return AnalyticsEvent.SIGNUP_STARTED
        elif path.startswith("/api/v1/auth/login") and method == "POST":
            return AnalyticsEvent.LOGIN
        elif path.startswith("/api/v1/auth/logout") and method == "POST":
            return AnalyticsEvent.LOGOUT

        # Generation events
        elif path.startswith("/api/v1/generation") and method == "POST":
            return AnalyticsEvent.GENERATION_STARTED

        # Payment events
        elif path.startswith("/api/v1/payments/create") and method == "POST":
            return AnalyticsEvent.PAYMENT_INITIATED

        # Referral events
        elif path.startswith("/api/v1/referrals") and method == "GET":
            return AnalyticsEvent.FEATURE_USED

        # User events
        elif path.startswith("/api/v1/users") and method in ["PUT", "PATCH"]:
            return AnalyticsEvent.USER_PROFILE_UPDATED

        return None

    def _get_client_ip(self, request: Request) -> str | None:
        """Extract client IP address from request."""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to client IP
        client = getattr(request, "client", None)
        if client is not None:
            return client.host

        return None


def add_session_id(request: Request) -> str:
    """Add or retrieve session ID from request state."""
    if not hasattr(request.state, "session_id"):
        request.state.session_id = str(uuid.uuid4())
    return cast(str, request.state.session_id)