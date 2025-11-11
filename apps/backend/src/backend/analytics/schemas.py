"""Analytics API schemas."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsEventBase(BaseModel):
    """Base analytics event schema."""
    
    event_type: str = Field(..., description="Type of analytics event")
    event_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Event data",
    )
    user_properties: dict[str, Any] | None = Field(
        default=None,
        description="User properties",
    )
    session_id: str | None = Field(
        default=None,
        description="Session identifier",
    )
    ip_address: str | None = Field(
        default=None,
        description="Client IP address",
    )
    user_agent: str | None = Field(
        default=None,
        description="Client user agent",
    )


class AnalyticsEventCreate(AnalyticsEventBase):
    """Schema for creating analytics events."""
    
    user_id: str | None = Field(default=None, description="User identifier")
    provider: str = Field(default="both", description="Analytics provider")


class AnalyticsEventResponse(AnalyticsEventBase):
    """Schema for analytics event responses."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(..., description="Event ID")
    user_id: str | None = Field(default=None, description="User identifier")
    provider: str = Field(..., description="Analytics provider")
    created_at: str = Field(..., description="Event creation timestamp")
    processed_at: str | None = Field(
        default=None,
        description="Event processing timestamp",
    )
    is_successful: bool = Field(
        ...,
        description="Whether event was successfully processed",
    )
    retry_count: int = Field(
        default=0,
        description="Number of retry attempts",
    )
    last_error: str | None = Field(
        default=None,
        description="Last error message",
    )


class AggregatedMetricsBase(BaseModel):
    """Base aggregated metrics schema."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    metric_date: date = Field(..., description="Metric date")
    metric_type: str = Field(..., description="Type of metric")
    period: str = Field(..., description="Time period (daily, weekly, monthly)")
    value: float = Field(..., description="Metric value")
    metric_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metric data",
        alias="metric_data",
    )


class AggregatedMetricsResponse(AggregatedMetricsBase):
    """Schema for aggregated metrics responses."""

    id: str = Field(..., description="Metric ID")
    created_at: str = Field(..., description="Metric creation timestamp")
    updated_at: str = Field(..., description="Metric update timestamp")


class AnalyticsDashboardResponse(BaseModel):
    """Schema for analytics dashboard data."""
    
    daily_active_users: int = Field(..., description="Daily active users")
    monthly_active_users: int = Field(..., description="Monthly active users")
    new_registrations_today: int = Field(
        ...,
        description="New registrations today",
    )
    revenue_today: float = Field(
        ...,
        description="Revenue generated today",
    )
    conversion_rate: float = Field(
        ...,
        description="Signup to payment conversion rate",
    )
    churn_rate: float = Field(
        ...,
        description="Customer churn rate",
    )
    ltv_cac_ratio: float = Field(
        ...,
        description="Lifetime value to customer acquisition cost ratio",
    )


class AnalyticsEventListResponse(BaseModel):
    """Schema for paginated analytics event list."""
    
    events: list[AnalyticsEventResponse] = Field(
        ...,
        description="List of analytics events",
    )
    total: int = Field(..., description="Total number of events")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of events per page")
    total_pages: int = Field(..., description="Total number of pages")


class AnalyticsMetricsResponse(BaseModel):
    """Schema for analytics metrics response."""
    
    metrics: dict[str, Any] = Field(..., description="Calculated metrics")
    period: str = Field(..., description="Time period for metrics")
    start_date: date = Field(..., description="Start date for metrics")
    end_date: date = Field(..., description="End date for metrics")


class AnalyticsConfigResponse(BaseModel):
    """Schema for analytics configuration response."""
    
    enabled: bool = Field(..., description="Whether analytics is enabled")
    amplitude_configured: bool = Field(
        ...,
        description="Whether Amplitude is configured",
    )
    mixpanel_configured: bool = Field(
        ...,
        description="Whether Mixpanel is configured",
    )
    pii_tracking_enabled: bool = Field(
        ...,
        description="Whether PII tracking is enabled",
    )
    sandbox_mode: bool = Field(
        ...,
        description="Whether sandbox mode is enabled",
    )
    batch_size: int = Field(
        ...,
        description="Batch size for event processing",
    )
    flush_interval_seconds: int = Field(
        ...,
        description="Flush interval in seconds",
    )