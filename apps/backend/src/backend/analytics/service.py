"""Analytics service for tracking events to Amplitude/Mixpanel."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, cast

import mixpanel  # type: ignore[import-untyped]
import structlog
from amplitude import Amplitude, BaseEvent, Identify  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.analytics.enums import AnalyticsEvent, AnalyticsProvider
from backend.analytics.models import AnalyticsEventRecord
from backend.analytics.repository import (
    create_analytics_event,
    get_pending_events,
    mark_event_failed,
    mark_event_processed,
)
from backend.core.config import Settings

logger = structlog.get_logger(__name__)

EventPayload = dict[str, Any]
UserProperties = dict[str, Any]
ProviderResponse = dict[str, Any]
ProviderResponseList = list[tuple[str, ProviderResponse]]


class AnalyticsError(Exception):
    """Base analytics service error."""


class ProviderConfigurationError(AnalyticsError):
    """Analytics provider not properly configured."""


class EventValidationError(AnalyticsError):
    """Event data validation failed."""


class AnalyticsService:
    """Service for tracking analytics events with batching and retry logic."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._amplitude_client: Amplitude | None = None
        self._mixpanel_client: mixpanel.Mixpanel | None = None
        self._initialize_clients()

    def _initialize_clients(self) -> None:
        """Initialize analytics provider clients."""
        if not self.settings.analytics.enabled:
            logger.info("Analytics service disabled")
            return

        # Initialize Amplitude
        if self.settings.analytics.amplitude_api_key:
            try:
                self._amplitude_client = Amplitude(
                    api_key=self.settings.analytics.amplitude_api_key.get_secret_value()
                )
                logger.info("Amplitude client initialized")
            except Exception as e:
                logger.error("Failed to initialize Amplitude client", error=str(e))

        # Initialize Mixpanel
        if self.settings.analytics.mixpanel_token:
            try:
                self._mixpanel_client = mixpanel.Mixpanel(
                    token=self.settings.analytics.mixpanel_token.get_secret_value()
                )
                logger.info("Mixpanel client initialized")
            except Exception as e:
                logger.error("Failed to initialize Mixpanel client", error=str(e))

        if not self._amplitude_client and not self._mixpanel_client:
            logger.warning("No analytics providers configured")

    def _validate_event_data(
        self,
        event_type: AnalyticsEvent,
        event_data: EventPayload,
    ) -> None:
        """Validate event data against PII policies."""
        if not self.settings.analytics.enable_pii_tracking:
            # Remove potential PII fields
            pii_fields = [
                "email",
                "name",
                "full_name",
                "first_name",
                "last_name",
                "phone",
            ]
            for field in pii_fields:
                event_data.pop(field, None)

        # Validate event type specific requirements
        required_fields = {
            AnalyticsEvent.SIGNUP_STARTED: ["signup_method"],
            AnalyticsEvent.GENERATION_STARTED: ["generation_type"],
            AnalyticsEvent.PAYMENT_INITIATED: ["amount", "currency"],
            AnalyticsEvent.REFERRAL_SENT: ["referral_code"],
        }

        if event_type in required_fields:
            for field in required_fields[event_type]:
                if field not in event_data:
                    raise EventValidationError(f"Missing required field: {field}")

    def _sanitize_user_properties(
        self,
        user_properties: UserProperties | None,
    ) -> UserProperties:
        """Sanitize user properties according to PII policies."""
        if not user_properties or not self.settings.analytics.enable_user_properties:
            return {}

        if not self.settings.analytics.enable_pii_tracking:
            # Remove PII fields
            pii_fields = [
                "email",
                "name",
                "full_name",
                "first_name",
                "last_name",
                "phone",
            ]
            sanitized = user_properties.copy()
            for field in pii_fields:
                sanitized.pop(field, None)
            return sanitized

        return user_properties

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    async def _send_to_amplitude(
        self,
        user_id: str | None,
        event_type: str,
        event_properties: EventPayload,
        user_properties: UserProperties | None = None,
    ) -> ProviderResponse:
        """Send event to Amplitude with retry logic."""
        if not self._amplitude_client:
            raise ProviderConfigurationError("Amplitude client not initialized")

        try:
            event = BaseEvent(
                event_type=event_type,
                user_id=user_id,
                event_properties=event_properties,
                user_properties=user_properties,
            )

            response = self._amplitude_client.track(event)

            if self.settings.analytics.sandbox_mode:
                logger.info(
                    "Amplitude event (sandbox mode)",
                    event_type=event_type,
                    user_id=user_id,
                    properties=event_properties,
                )
                return {"status": "success", "sandbox": True}

            if isinstance(response, dict):
                return cast(ProviderResponse, response)
            return {"status": "success"}

        except Exception as e:
            logger.error(
                "Failed to send event to Amplitude",
                event_type=event_type,
                user_id=user_id,
                error=str(e),
            )
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    async def _send_to_mixpanel(
        self,
        user_id: str | None,
        event_type: str,
        event_properties: EventPayload,
        user_properties: UserProperties | None = None,
    ) -> ProviderResponse:
        """Send event to Mixpanel with retry logic."""
        if not self._mixpanel_client:
            raise ProviderConfigurationError("Mixpanel client not initialized")

        try:
            if self.settings.analytics.sandbox_mode:
                logger.info(
                    "Mixpanel event (sandbox mode)",
                    event_type=event_type,
                    user_id=user_id,
                    properties=event_properties,
                )
                return {"status": "success", "sandbox": True}

            # Track event
            self._mixpanel_client.track(
                distinct_id=user_id or "anonymous",
                event_name=event_type,
                properties=event_properties,
            )

            # Set user properties if provided
            if user_properties and user_id:
                self._mixpanel_client.people_set(
                    distinct_id=user_id,
                    properties=user_properties,
                )

            return {"status": "success"}

        except Exception as e:
            logger.error(
                "Failed to send event to Mixpanel",
                event_type=event_type,
                user_id=user_id,
                error=str(e),
            )
            raise

    async def track_event(
        self,
        session: AsyncSession,
        event_type: AnalyticsEvent,
        event_data: EventPayload,
        user_id: str | None = None,
        user_properties: UserProperties | None = None,
        provider: AnalyticsProvider = AnalyticsProvider.BOTH,
        session_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AnalyticsEventRecord:
        """Track an analytics event with batching support."""
        if not self.settings.analytics.enabled:
            logger.debug(
                "Analytics disabled, skipping event",
                event_type=event_type.value,
            )
            # Return a dummy event model for consistency
            user_uuid = None
            if user_id:
                try:
                    user_uuid = uuid.UUID(user_id)
                except ValueError:
                    user_uuid = None

            return AnalyticsEventRecord(
                user_id=user_uuid,
                event_type=event_type,
                provider=provider,
                event_data=event_data,
                user_properties=user_properties,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
                is_successful=True,
            )

        try:
            # Validate event data
            self._validate_event_data(event_type, event_data.copy())
            sanitized_user_properties = self._sanitize_user_properties(user_properties)

            # Store event for batch processing
            analytics_event = await create_analytics_event(
                session=session,
                user_id=user_id,
                event_type=event_type,
                provider=provider,
                event_data=event_data,
                user_properties=sanitized_user_properties,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            logger.info(
                "Analytics event queued",
                event_id=str(analytics_event.id),
                event_type=event_type.value,
                user_id=user_id,
                provider=provider.value,
            )

            return analytics_event

        except Exception as e:
            logger.error(
                "Failed to track analytics event",
                event_type=event_type.value,
                user_id=user_id,
                error=str(e),
            )
            raise AnalyticsError(f"Failed to track event: {e}") from e

    async def process_pending_events(self, session: AsyncSession) -> dict[str, int]:
        """Process pending analytics events with batch sending."""
        if not self.settings.analytics.enabled:
            return {"processed": 0, "failed": 0}

        pending_events = await get_pending_events(
            session=session,
            batch_size=self.settings.analytics.batch_size,
            max_retries=self.settings.analytics.max_retries,
        )

        processed_count = 0
        failed_count = 0

        for event in pending_events:
            try:
                user_id_str = str(event.user_id) if event.user_id is not None else None
                user_properties: UserProperties = dict(event.user_properties or {})
                event_properties: EventPayload = dict(event.event_data)

                # Send to specified providers
                responses: ProviderResponseList = []
                if event.provider in [
                    AnalyticsProvider.AMPLITUDE,
                    AnalyticsProvider.BOTH,
                ]:
                    if self._amplitude_client:
                        response = await self._send_to_amplitude(
                            user_id=user_id_str,
                            event_type=event.event_type.value,
                            event_properties=event_properties,
                            user_properties=user_properties,
                        )
                        responses.append(("amplitude", response))

                if event.provider in [
                    AnalyticsProvider.MIXPANEL,
                    AnalyticsProvider.BOTH,
                ]:
                    if self._mixpanel_client:
                        response = await self._send_to_mixpanel(
                            user_id=user_id_str,
                            event_type=event.event_type.value,
                            event_properties=event_properties,
                            user_properties=user_properties,
                        )
                        responses.append(("mixpanel", response))

                # Mark as processed
                provider_response_payload: Mapping[str, object] = {
                    "responses": responses
                }
                await mark_event_processed(
                    session=session,
                    event_id=event.id,
                    provider_response=dict(provider_response_payload),
                )
                processed_count += 1

                logger.debug(
                    "Analytics event processed",
                    event_id=str(event.id),
                    event_type=event.event_type.value,
                    providers=[r[0] for r in responses],
                )

            except Exception as e:
                # Mark as failed
                await mark_event_failed(
                    session=session,
                    event_id=event.id,
                    error_message=str(e),
                )
                failed_count += 1

                logger.error(
                    "Failed to process analytics event",
                    event_id=str(event.id),
                    event_type=event.event_type.value,
                    error=str(e),
                    retry_count=event.retry_count,
                )

        await session.commit()

        logger.info(
            "Analytics batch processing completed",
            processed=processed_count,
            failed=failed_count,
            total=len(pending_events),
        )

        return {"processed": processed_count, "failed": failed_count}

    async def update_user_properties(
        self,
        user_id: str,
        properties: UserProperties,
        provider: AnalyticsProvider = AnalyticsProvider.BOTH,
    ) -> None:
        """Update user properties in analytics providers."""
        if not self.settings.analytics.enabled:
            return

        sanitized_properties = self._sanitize_user_properties(properties)
        if not sanitized_properties:
            logger.debug("No user properties to update after PII filtering")
            return

        try:
            if provider in [AnalyticsProvider.AMPLITUDE, AnalyticsProvider.BOTH]:
                if self._amplitude_client:
                    identify = Identify()
                    for key, value in sanitized_properties.items():
                        identify.set(key, value)

                    self._amplitude_client.identify(
                        identify=identify,
                        user_id=user_id,
                    )

            if provider in [AnalyticsProvider.MIXPANEL, AnalyticsProvider.BOTH]:
                if self._mixpanel_client:
                    self._mixpanel_client.people_set(
                        distinct_id=user_id,
                        properties=sanitized_properties,
                    )

            logger.info(
                "User properties updated",
                user_id=user_id,
                provider=provider.value,
                properties=list(sanitized_properties.keys()),
            )

        except Exception as e:
            logger.error(
                "Failed to update user properties",
                user_id=user_id,
                provider=provider.value,
                error=str(e),
            )
            raise AnalyticsError(f"Failed to update user properties: {e}") from e
