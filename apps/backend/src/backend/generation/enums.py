from __future__ import annotations

from enum import StrEnum

__all__ = ["GenerationTaskStatus", "GenerationEventType"]


class GenerationTaskStatus(StrEnum):
    """Lifecycle states tracked for generation tasks."""

    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationEventType(StrEnum):
    """Audit trail markers for generation task transitions."""

    CREATED = "created"
    ENQUEUED = "enqueued"
    STORAGE_UPLOADED = "storage_uploaded"
    QUEUE_PUBLISHED = "queue_published"
    FAILED = "failed"
