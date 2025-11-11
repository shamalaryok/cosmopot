"""Analytics decorators for manual event tracking."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, ParamSpec, TypeVar, cast

from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.enums import AnalyticsEvent
from backend.analytics.service import AnalyticsService

P = ParamSpec("P")
T = TypeVar("T")

SESSION_PARAM_NAMES: tuple[str, ...] = ("session", "db", "db_session")
USER_PARAM_NAMES: tuple[str, ...] = ("user", "current_user")


def _resolve_argument_value(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
    candidate_names: tuple[str, ...],
) -> object | None:
    """Resolve an argument passed to the wrapped function."""
    for name in candidate_names:
        if name in kwargs:
            return cast(object, kwargs[name])

    try:
        bound_arguments = inspect.signature(func).bind_partial(*args, **kwargs)
    except TypeError:
        return None

    for name in candidate_names:
        if name in bound_arguments.arguments:
            return cast(object, bound_arguments.arguments[name])

    return None


def _extract_user_id(candidate: object | None, include_user: bool) -> str | None:
    """Extract a string user identifier from an arbitrary object."""
    if not include_user or candidate is None:
        return None

    identifier = getattr(candidate, "id", None)
    if identifier is None:
        return None
    return str(identifier)


async def _track_event_with_session(
    session: AsyncSession,
    event_type: AnalyticsEvent,
    event_data: Mapping[str, Any],
    user_id: str | None,
) -> None:
    """Safely track analytics events, swallowing provider errors."""
    try:
        from backend.core.config import get_settings

        settings = get_settings()
        analytics_service = AnalyticsService(settings)
        await analytics_service.track_event(
            session=session,
            event_type=event_type,
            event_data=dict(event_data),
            user_id=user_id,
        )
        await session.commit()
    except Exception:
        # Analytics failures must never break the primary execution path.
        pass


def track_analytics_event(
    event_type: AnalyticsEvent,
    event_data_mapper: Callable[P, Mapping[str, Any]] | None = None,
    include_user: bool = True,
    include_request_data: bool = False,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]: 
    """Decorator to automatically track analytics events for function calls."""
    
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            args_tuple = cast(tuple[Any, ...], args)
            kwargs_mapping = cast(dict[str, Any], kwargs)
            session_raw = _resolve_argument_value(func, args_tuple, kwargs_mapping, SESSION_PARAM_NAMES)
            user_raw = _resolve_argument_value(func, args_tuple, kwargs_mapping, USER_PARAM_NAMES)

            session: AsyncSession | None = (
                session_raw
                if isinstance(session_raw, AsyncSession)
                else None
            )
            user_id = _extract_user_id(user_raw, include_user)

            event_data: dict[str, Any] = {}
            if event_data_mapper:
                try:
                    mapped_data = event_data_mapper(*args, **kwargs)
                    event_data.update(mapped_data)
                except Exception:
                    pass

            if include_request_data:
                event_data.update({
                    "function": func.__name__,
                    "module": func.__module__,
                })

            if session is not None:
                await _track_event_with_session(session, event_type, event_data, user_id)

            try:
                return await func(*args, **kwargs)
            except BaseException as e:
                if session is not None:
                    failure_event_data = dict(event_data)
                    failure_event_data.update({
                        "error": str(e),
                        "error_type": type(e).__name__,
                    })
                    failure_event_type = _get_failure_event_type(event_type)
                    await _track_event_with_session(session, failure_event_type, failure_event_data, user_id)
                raise

        return async_wrapper

    return decorator


def _get_failure_event_type(success_event_type: AnalyticsEvent) -> AnalyticsEvent:
    """Map success event types to corresponding failure event types."""
    failure_mapping = {
        AnalyticsEvent.SIGNUP_STARTED: AnalyticsEvent.SIGNUP_COMPLETED,
        AnalyticsEvent.GENERATION_STARTED: AnalyticsEvent.GENERATION_FAILED,
        AnalyticsEvent.PAYMENT_INITIATED: AnalyticsEvent.PAYMENT_FAILED,
    }
    
    return failure_mapping.get(success_event_type, success_event_type)


class AnalyticsTracker:
    """Helper class for manual analytics tracking."""
    
    def __init__(self, analytics_service: AnalyticsService, session: AsyncSession) -> None:
        self.analytics_service = analytics_service
        self.session = session
    
    async def track_signup(
        self,
        user_id: str,
        signup_method: str = "email",
        user_properties: dict[str, Any] | None = None,
        **additional_data: Any,
    ) -> None:
        """Track user signup event."""
        event_data = {
            "signup_method": signup_method,
            **additional_data,
        }
        
        await self.analytics_service.track_event(
            session=self.session,
            event_type=AnalyticsEvent.SIGNUP_COMPLETED,
            event_data=event_data,
            user_id=user_id,
            user_properties=user_properties,
        )
    
    async def track_login(
        self,
        user_id: str,
        login_method: str = "email",
        **additional_data: Any,
    ) -> None:
        """Track user login event."""
        event_data = {
            "login_method": login_method,
            **additional_data,
        }
        
        await self.analytics_service.track_event(
            session=self.session,
            event_type=AnalyticsEvent.LOGIN,
            event_data=event_data,
            user_id=user_id,
        )
    
    async def track_generation(
        self,
        user_id: str,
        generation_type: str,
        status: str = "started",
        **additional_data: Any,
    ) -> None:
        """Track generation event."""
        event_type = AnalyticsEvent.GENERATION_STARTED
        
        if status == "completed":
            event_type = AnalyticsEvent.GENERATION_COMPLETED
        elif status == "failed":
            event_type = AnalyticsEvent.GENERATION_FAILED
        elif status == "cancelled":
            event_type = AnalyticsEvent.GENERATION_CANCELLED
        
        event_data = {
            "generation_type": generation_type,
            "status": status,
            **additional_data,
        }
        
        await self.analytics_service.track_event(
            session=self.session,
            event_type=event_type,
            event_data=event_data,
            user_id=user_id,
        )
    
    async def track_payment(
        self,
        user_id: str,
        amount: float,
        currency: str,
        status: str = "initiated",
        payment_method: str = "card",
        **additional_data: Any,
    ) -> None:
        """Track payment event."""
        event_type = AnalyticsEvent.PAYMENT_INITIATED
        
        if status == "completed":
            event_type = AnalyticsEvent.PAYMENT_COMPLETED
        elif status == "failed":
            event_type = AnalyticsEvent.PAYMENT_FAILED
        
        event_data = {
            "amount": amount,
            "currency": currency,
            "payment_method": payment_method,
            "status": status,
            **additional_data,
        }
        
        await self.analytics_service.track_event(
            session=self.session,
            event_type=event_type,
            event_data=event_data,
            user_id=user_id,
        )
    
    async def track_referral(
        self,
        user_id: str,
        referral_code: str,
        action: str = "sent",
        **additional_data: Any,
    ) -> None:
        """Track referral event."""
        event_type = AnalyticsEvent.REFERRAL_SENT
        
        if action == "accepted":
            event_type = AnalyticsEvent.REFERRAL_ACCEPTED
        elif action == "milestone":
            event_type = AnalyticsEvent.REFERRAL_MILESTONE_REACHED
        
        event_data = {
            "referral_code": referral_code,
            "action": action,
            **additional_data,
        }
        
        await self.analytics_service.track_event(
            session=self.session,
            event_type=event_type,
            event_data=event_data,
            user_id=user_id,
        )
    
    async def track_feature_usage(
        self,
        user_id: str,
        feature_name: str,
        **additional_data: Any,
    ) -> None:
        """Track feature usage event."""
        event_data = {
            "feature_name": feature_name,
            **additional_data,
        }
        
        await self.analytics_service.track_event(
            session=self.session,
            event_type=AnalyticsEvent.FEATURE_USED,
            event_data=event_data,
            user_id=user_id,
        )
    
    async def update_user_properties(
        self,
        user_id: str,
        properties: dict[str, Any],
    ) -> None:
        """Update user properties in analytics providers."""
        await self.analytics_service.update_user_properties(
            user_id=user_id,
            properties=properties,
        )