"""Analytics database models."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.analytics.enums import AnalyticsEvent, AnalyticsProvider
from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from backend.db.types import GUID, UTCDateTime

if TYPE_CHECKING:
    from backend.auth.models import User


class AnalyticsEventRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stored analytics event for batching and retry logic."""

    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_user_id", "user_id"),
        Index("ix_analytics_events_event_type", "event_type"),
        Index("ix_analytics_events_provider", "provider"),
        Index("ix_analytics_events_created_at", "created_at"),
        Index("ix_analytics_events_processed_at", "processed_at"),
        Index("ix_analytics_events_retry_count", "retry_count"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[AnalyticsEvent] = mapped_column(
        Enum(AnalyticsEvent, name="analytics_event_type", native_enum=False),
        nullable=False,
    )
    provider: Mapped[AnalyticsProvider] = mapped_column(
        Enum(AnalyticsProvider, name="analytics_event_provider", native_enum=False),
        nullable=False,
        default=AnalyticsProvider.BOTH,
    )
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    user_properties: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    processed_at: Mapped[dt.datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    provider_response: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User | None] = relationship("User", lazy="selectin")


class AggregatedMetrics(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Daily/weekly/monthly aggregated analytics metrics."""

    __tablename__ = "analytics_aggregated_metrics"
    __table_args__ = (
        Index("ix_analytics_aggregated_metrics_date", "metric_date"),
        Index("ix_analytics_aggregated_metrics_type", "metric_type"),
        Index("ix_analytics_aggregated_metrics_period", "period"),
        UniqueConstraint(
            "metric_date",
            "metric_type",
            "period",
            name="uq_analytics_aggregated_metrics_date_type_period",
        ),
    )

    metric_date: Mapped[dt.date] = mapped_column(Date(), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(100), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    metric_data: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
