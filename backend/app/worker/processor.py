from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from user_service import repository
from user_service.enums import GenerationTaskStatus
from user_service.models import GenerationTask
from user_service.schemas import (
    GenerationTaskFailureUpdate,
    GenerationTaskResultUpdate,
)

from .banana import GeminiNanoError
from .bootstrap import RuntimeState
from .images import ImageProcessingError, generate_thumbnail
from .logging import get_logger
from .redis_events import RedisNotifier
from .storage import StorageError, parse_s3_url


@dataclass(slots=True)
class ProcessingOutcome:
    status: str
    details: dict[str, Any]


class TaskNotFoundError(RuntimeError):
    """Raised when the requested task does not exist."""


class GenerationTaskProcessor:
    """Execute the generation pipeline for a single task."""

    def __init__(self, task_id: int, runtime: RuntimeState) -> None:
        self.task_id = task_id
        self._runtime = runtime
        self._log = get_logger(__name__).bind(task_id=task_id)
        self._settings = runtime.settings
        self._subscription_id: int | None = None
        self._quota_incremented = False

    def run(self) -> ProcessingOutcome:
        return asyncio.run(self._run())

    async def _run(self) -> ProcessingOutcome:
        notifier = self._runtime.notifier
        if not await notifier.acquire_task(self.task_id):
            self._log.info("duplicate-task-dropped")
            return ProcessingOutcome(
                status="duplicate", details={"task_id": self.task_id}
            )

        await notifier.publish_status("accepted", {"task_id": self.task_id})

        try:
            return await self._process(notifier)
        finally:
            await notifier.release_task(self.task_id)

    async def _process(self, notifier: RedisNotifier) -> ProcessingOutcome:
        session: AsyncSession | None = None
        try:
            session = self._runtime.session_factory()
            task = await repository.get_generation_task_by_id(session, self.task_id)
            if task is None:
                await notifier.publish_dead_letter(
                    {"task_id": self.task_id, "error": "task-not-found"}
                )
                raise TaskNotFoundError(f"task {self.task_id} not found")

            if task.status == GenerationTaskStatus.SUCCEEDED:
                self._log.info("task-already-complete")
                return ProcessingOutcome(
                    status="already-complete", details={"task_id": self.task_id}
                )

            await repository.mark_generation_task_started(session, task)
            await session.commit()
            await notifier.publish_status("running", {"task_id": self.task_id})

            subscription = await repository.get_active_subscription_for_user(
                session, task.user_id
            )
            if subscription is not None:
                await repository.increment_subscription_usage(session, subscription, 1)
                await session.commit()
                self._subscription_id = subscription.id
                self._quota_incremented = True

            outcome = await self._execute_pipeline(session, task)
            details: dict[str, Any] = dict(outcome.details)
            await notifier.publish_status("succeeded", details)
            return outcome
        except Exception as exc:
            message = await self._handle_failure(session, notifier, exc)
            return ProcessingOutcome(
                status="failed",
                details={"task_id": self.task_id, "error": message},
            )
        finally:
            if session is not None:
                await session.close()

    async def _execute_pipeline(
        self, session: AsyncSession, task: GenerationTask
    ) -> ProcessingOutcome:
        if not task.input_asset_url:
            raise StorageError("Task is missing input asset URL")

        input_location = parse_s3_url(task.input_asset_url)
        storage = self._runtime.storage
        banana = self._runtime.banana_client

        input_bytes = await storage.download(input_location.bucket, input_location.key)
        payload = self._prepare_model_payload(task, input_bytes)
        result = banana.generate(payload)

        thumbnail_bytes = generate_thumbnail(
            result.image_bytes,
            size=self._settings.thumbnail_size,
            image_format="JPEG",
        )

        result_key = f"{self._settings.result_prefix}/{task.id}.jpg"
        thumbnail_key = f"{self._settings.thumbnail_prefix}/{task.id}.jpg"

        result_url = await storage.upload(
            self._settings.s3_bucket, result_key, result.image_bytes, "image/jpeg"
        )
        thumb_url = await storage.upload(
            self._settings.s3_bucket, thumbnail_key, thumbnail_bytes, "image/jpeg"
        )

        update = GenerationTaskResultUpdate(
            result_asset_url=result_url,
            result_parameters={
                "thumbnail_url": thumb_url,
                "metadata": dict(result.metadata),
            },
        )
        await repository.mark_generation_task_succeeded(session, task, update)
        await session.commit()

        details = {
            "task_id": self.task_id,
            "result_url": result_url,
            "thumbnail_url": thumb_url,
            "metadata": dict(result.metadata),
        }
        return ProcessingOutcome(status="succeeded", details=details)

    def _prepare_model_payload(
        self, task: GenerationTask, input_bytes: bytes
    ) -> dict[str, Any]:
        input_base64 = base64.b64encode(input_bytes).decode("utf-8")
        payload = {
            "parameters": dict(task.parameters),
            "input_asset": task.input_asset_url,
            "input_base64": input_base64,
        }
        return payload

    async def _handle_failure(
        self,
        session: AsyncSession | None,
        notifier: RedisNotifier,
        exc: Exception,
    ) -> str:
        message = self._map_error(exc)
        self._log.error("task-processing-failed", error=message)

        if session is None:
            await notifier.publish_dead_letter(
                {"task_id": self.task_id, "error": message}
            )
            return message

        await session.rollback()

        task = await repository.get_generation_task_by_id(session, self.task_id)
        if task is None:
            await notifier.publish_dead_letter(
                {"task_id": self.task_id, "error": message}
            )
            return message

        subscription = None
        if self._subscription_id is not None:
            subscription = await repository.get_subscription_by_id(
                session, self._subscription_id
            )
        elif self._quota_incremented:
            subscription = await repository.get_active_subscription_for_user(
                session, task.user_id
            )

        if self._quota_incremented and subscription is not None:
            await repository.decrement_subscription_usage(session, subscription, 1)
            self._quota_incremented = False

        failure_payload = GenerationTaskFailureUpdate(
            error=message,
            result_parameters={"previous_status": task.status.value},
        )
        await repository.mark_generation_task_failed(session, task, failure_payload)
        await session.commit()

        await notifier.publish_status(
            "failed",
            {"task_id": self.task_id, "error": message},
        )
        await notifier.publish_dead_letter(
            {
                "task_id": self.task_id,
                "error": message,
                "category": self._categorise_error(exc),
            }
        )
        return message

    def _map_error(self, exc: Exception) -> str:
        if isinstance(exc, GeminiNanoError):
            return "gemini-nano-error"
        if isinstance(exc, StorageError):
            return "storage-error"
        if isinstance(exc, ImageProcessingError):
            return "image-processing-error"
        return "unexpected-error"

    def _categorise_error(self, exc: Exception) -> str:
        if isinstance(exc, GeminiNanoError):
            return "model"
        if isinstance(exc, StorageError):
            return "storage"
        if isinstance(exc, ImageProcessingError):
            return "image"
        return "unknown"
