"""Analytics dependencies for FastAPI dependency injection."""

from __future__ import annotations

from functools import lru_cache

from backend.analytics.aggregation import AnalyticsAggregationService
from backend.analytics.service import AnalyticsService
from backend.core.config import get_settings


@lru_cache
def get_analytics_service() -> AnalyticsService:
    """Get analytics service instance."""
    settings = get_settings()
    return AnalyticsService(settings)


@lru_cache
def get_analytics_aggregation_service() -> AnalyticsAggregationService:
    """Get analytics aggregation service instance."""
    return AnalyticsAggregationService()