from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from typing import Any, ParamSpec, Protocol, TypeVar, cast

from celery import Task, states
from celery.result import AsyncResult

from .celery_app import celery_app
from .constants import TASK_NAMESPACE
from .worker import bootstrap
from .worker.logging import get_logger
from .worker.processor import GenerationTaskProcessor

logger = get_logger(__name__)

from backend.core.config import get_settings
from backend.security import GDPRDataExporter, PurgeOldAssetsPayload

P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)


class RegisteredTask(Protocol[P, R_co]):
    name: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R_co: ...

    def delay(self, *args: P.args, **kwargs: P.kwargs) -> AsyncResult[R_co]: ...

    def apply_async(
        self,
        args: tuple[Any, ...] | None = ...,
        kwargs: dict[str, Any] | None = ...,
        **options: Any,
    ) -> AsyncResult[R_co]: ...


def typed_task(
    *,
    name: str,
    bind: bool = False,
) -> Callable[[Callable[P, R_co]], RegisteredTask[P, R_co]]:
    raw_decorator = celery_app.task(name=name, bind=bind)
    return cast(Callable[[Callable[P, R_co]], RegisteredTask[P, R_co]], raw_decorator)


@typed_task(name=f"{TASK_NAMESPACE}.ping")
def ping(message: str = "pong") -> dict[str, str]:
    return {"message": message}


@typed_task(name=f"{TASK_NAMESPACE}.compute_sum")
def compute_sum(a: int, b: int) -> int:
    time.sleep(1)
    return a + b


@typed_task(name=f"{TASK_NAMESPACE}.unreliable")
def unreliable_task() -> str:
    time.sleep(1)
    if random.random() < 0.5:
        raise RuntimeError("Unlucky run, try again")
    return "Completed"


@typed_task(name=f"{TASK_NAMESPACE}.process_generation_task", bind=True)
def process_generation_task(task: Task, task_id: int) -> dict[str, Any]:
    runtime = bootstrap.get_runtime()
    processor = GenerationTaskProcessor(task_id, runtime)
    outcome = processor.run()
    result: dict[str, Any] = dict(outcome.details)
    result["status"] = outcome.status
    if outcome.status == "failed":
        logger.warning("generation-task-failed", task_id=task_id, details=result)
        task.update_state(state=states.FAILURE, meta=result)
    else:
        logger.info("generation-task-completed", task_id=task_id, details=result)
    return result


@typed_task(name=f"{TASK_NAMESPACE}.purge_old_s3_assets")
def purge_old_s3_assets(retention_days: int | None = None) -> PurgeOldAssetsPayload:
    """
    Scheduled task to purge S3 assets older than retention period.

    Args:
        retention_days: Days to retain; if None, uses GDPR result retention setting
    """
    try:
        settings = get_settings()
        exporter = GDPRDataExporter(settings)

        days = retention_days or settings.gdpr.result_retention_days
        result: PurgeOldAssetsPayload = asyncio.run(exporter.purge_old_assets(days))

        logger.info("s3_purge_task_completed", result=result)
        return result
    except Exception:
        logger.exception("s3_purge_task_failed")
        raise
