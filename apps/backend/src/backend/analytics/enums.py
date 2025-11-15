"""Analytics event and provider enums."""

from enum import StrEnum


class AnalyticsProvider(StrEnum):
    """Supported analytics providers."""

    AMPLITUDE = "amplitude"
    MIXPANEL = "mixpanel"
    BOTH = "both"


class AnalyticsEvent(StrEnum):
    """Standard analytics events."""

    # Authentication events
    SIGNUP_STARTED = "signup_started"
    SIGNUP_COMPLETED = "signup_completed"
    EMAIL_VERIFIED = "email_verified"
    LOGIN = "login"
    LOGOUT = "logout"
    SESSION_CREATED = "session_created"

    # Generation events
    GENERATION_STARTED = "generation_started"
    GENERATION_COMPLETED = "generation_completed"
    GENERATION_FAILED = "generation_failed"
    GENERATION_CANCELLED = "generation_cancelled"

    # Payment events
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_COMPLETED = "payment_completed"
    PAYMENT_FAILED = "payment_failed"
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUBSCRIPTION_UPGRADED = "subscription_upgraded"
    SUBSCRIPTION_DOWNGRADED = "subscription_downgraded"

    # Referral events
    REFERRAL_SENT = "referral_sent"
    REFERRAL_ACCEPTED = "referral_accepted"
    REFERRAL_MILESTONE_REACHED = "referral_milestone_reached"
    REFERRAL_EARNINGS_WITHDRAWN = "referral_earnings_withdrawn"

    # User engagement events
    PAGE_VIEW = "page_view"
    FEATURE_USED = "feature_used"
    SESSION_DURATION = "session_duration"
    USER_PROFILE_UPDATED = "user_profile_updated"
    SETTINGS_CHANGED = "settings_changed"

    # Business metrics
    DAILY_ACTIVE_USER = "daily_active_user"
    MONTHLY_ACTIVE_USER = "monthly_active_user"
    USER_ACQUISITION = "user_acquisition"
    USER_CHURN = "user_churn"
    REVENUE_GENERATED = "revenue_generated"
