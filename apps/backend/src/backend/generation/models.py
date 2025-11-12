from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import (
    Base,
    JSONDataMixin,
    MetadataAliasMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from backend.db.types import JSONType

from .enums import GenerationEventType, GenerationTaskStatus

__all__ = ["GenerationTask", "GenerationTaskEvent"]


class GenerationTask(Base, MetadataAliasMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persistent representation of an image generation request."""

    __tablename__ = "generation_tasks"
    __table_args__ = (
        Index("ix_generation_tasks_user_id", "user_id"),
        Index("ix_generation_tasks_status", "status"),
        Index("ix_generation_tasks_prompt_id", "prompt_id"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prompt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False
    )
    prompt: Mapped[str] = mapped_column(String(1024), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONType(), default=dict, nullable=False
    )
    status: Mapped[GenerationTaskStatus] = mapped_column(
        Enum(GenerationTaskStatus, name="generation_task_status", native_enum=False),
        nullable=False,
        default=GenerationTaskStatus.PENDING,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subscription_tier: Mapped[str] = mapped_column(String(64), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    input_url: Mapped[str | None] = mapped_column(String(2048))
    meta_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType(), default=dict, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(String(512))

    events: Mapped[list[GenerationTaskEvent]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class GenerationTaskEvent(UUIDPrimaryKeyMixin, TimestampMixin, JSONDataMixin, Base):
    """Audit trail entry capturing significant task lifecycle transitions."""

    __tablename__ = "generation_task_events"
    __table_args__ = (
        Index("ix_generation_task_events_task_id", "task_id"),
        Index("ix_generation_task_events_event_type", "event_type"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[GenerationEventType] = mapped_column(
        Enum(GenerationEventType, name="generation_task_event_type", native_enum=False),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(String(255), nullable=False)

    task: Mapped[GenerationTask] = relationship(back_populates="events")
