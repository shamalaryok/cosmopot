"""Add analytics tables

Revision ID: add_analytics_tables
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "add_analytics_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create analytics_events table
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("event_data", sa.JSON(), nullable=False),
        sa.Column("user_properties", sa.JSON(), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_response", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("is_successful", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analytics_events_created_at"), "analytics_events", ["created_at"], unique=False)
    op.create_index(op.f("ix_analytics_events_event_type"), "analytics_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_analytics_events_processed_at"), "analytics_events", ["processed_at"], unique=False)
    op.create_index(op.f("ix_analytics_events_provider"), "analytics_events", ["provider"], unique=False)
    op.create_index(op.f("ix_analytics_events_retry_count"), "analytics_events", ["retry_count"], unique=False)
    op.create_index(op.f("ix_analytics_events_user_id"), "analytics_events", ["user_id"], unique=False)

    # Create analytics_aggregated_metrics table
    op.create_table(
        "analytics_aggregated_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_type", sa.String(length=100), nullable=False),
        sa.Column("period", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("metric_date", "metric_type", "period", name="uq_analytics_aggregated_metrics_date_type_period"),
    )
    op.create_index(op.f("ix_analytics_aggregated_metrics_date"), "analytics_aggregated_metrics", ["metric_date"], unique=False)
    op.create_index(op.f("ix_analytics_aggregated_metrics_period"), "analytics_aggregated_metrics", ["period"], unique=False)
    op.create_index(op.f("ix_analytics_aggregated_metrics_type"), "analytics_aggregated_metrics", ["metric_type"], unique=False)


def downgrade() -> None:
    # Drop analytics_aggregated_metrics table
    op.drop_table("analytics_aggregated_metrics")
    
    # Drop analytics_events table
    op.drop_index(op.f("ix_analytics_events_user_id"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_retry_count"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_processed_at"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_provider"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_event_type"), table_name="analytics_events")
    op.drop_index(op.f("ix_analytics_events_created_at"), table_name="analytics_events")
    op.drop_table("analytics_events")