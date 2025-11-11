"""Analytics decorators for manual event tracking."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.enums import AnalyticsEvent
from backend.analytics.service import AnalyticsService

P = ParamSpec("P")
T = TypeVar("T")


def track_analytics_event(
    event_type: AnalyticsEvent,
    event_data_mapper: Callable[P, dict[str, Any]] | None = None,
    include_user: bool = True,
    include_request_data: bool = False,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator to automatically track analytics events for function calls."""
    
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Extract session from kwargs or function signature
            session = None
            user = None
            
            # Try to get session from common parameter names
            for param_name in ["session", "db", "db_session"]:
                if param_name in kwargs:
                    session = kwargs[param_name]
                    break
            
            # Try to get user from common parameter names
            for param_name in ["user", "current_user"]:
                if param_name in kwargs:
                    user = kwargs[param_name]
                    break
            
            # Try to extract from function signature if not found in kwargs
            if not session:
                sig = inspect.signature(func)
                for param_name, _param in sig.parameters.items():
                    if (
                        param_name in ["session", "db", "db_session"]
                        and param_name in kwargs
                    ):
                        session = kwargs[param_name]
                    elif (
                        param_name in ["user", "current_user"]
                        and param_name in kwargs
                    ):
                        user = kwargs[param_name]
            
            # Prepare event data
            event_data = {}
            
            if event_data_mapper:
                try:
                    mapped_data = event_data_mapper(*args, **kwargs)
                    if isinstance(mapped_data, dict):
                        event_data.update(mapped_data)
                except Exception:
                    # Ignore mapping errors to not break the main function
                    pass
            
            if include_request_data:
                event_data.update({
                    "function": func.__name__,
                    "module": func.__module__,
                })
            
            # Track the event before function execution
            if session and isinstance(session, AsyncSession):
                try:
                    # Get analytics service - this is a bit of a hack
                    # In practice, you'd want to inject this properly
                    from backend.core.config import get_settings
                    settings = get_settings()
                    analytics_service = AnalyticsService(settings)
                    
                    user_id = str(user.id) if include_user and user else None
                    
                    await analytics_service.track_event(
                        session=session,
                        event_type=event_type,
                        event_data=event_data,
                        user_id=user_id,
                    )
                    await session.commit()
                except Exception:
                    # Don't let analytics errors break the main function
                    pass
            
            # Execute the original function
            try:
                result = await func(*args, **kwargs)
                return result
            except BaseException as e:
                # Track failure if needed
                if session and isinstance(session, AsyncSession):
                    try:
                        failure_event_data = event_data.copy()
                        failure_event_data.update({
                            "error": str(e),
                            "error_type": type(e).__name__,
                        })
                        
                        # Map to appropriate failure event
                        failure_event_type = _get_failure_event_type(event_type)
                        
                        from backend.core.config import get_settings
                        settings = get_settings()
                        analytics_service = AnalyticsService(settings)
                        
                        user_id = str(user.id) if include_user and user else None
                        
                        await analytics_service.track_event(
                            session=session,
                            event_type=failure_event_type,
                            event_data=failure_event_data,
                            user_id=user_id,
                        )
                        await session.commit()
                    except BaseException:
                        # Don't let analytics errors break the main function
                        pass
                
                # Re-raise the original exception
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
    
    def __init__(self, analytics_service: AnalyticsService, session: AsyncSession):
        self.analytics_service = analytics_service
        self.session = session
    
    async def track_signup(
        self,
        user_id: str,
        signup_method: str = "email",
        user_properties: dict[str, Any] | None = None,
        **additional_data,
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
        **additional_data,
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
        **additional_data,
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
        **additional_data,
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
        **additional_data,
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
        **additional_data,
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