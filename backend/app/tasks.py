from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, cast

from celery import Task, states

from .celery_app import celery_app
from .constants import TASK_NAMESPACE
from .worker import bootstrap
from .worker.logging import get_logger
from .worker.processor import GenerationTaskProcessor

logger = get_logger(__name__)

try:
    from backend.core.config import get_settings
    from backend.security import GDPRDataExporter
except ImportError:
    pass

P = ParamSpec("P")
R = TypeVar("R")


def typed_task(
    *,
    name: str,
    bind: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    raw_decorator = cast(
        Callable[[Callable[P, R]], Callable[P, R]],
        celery_app.task(name=name, bind=bind),
    )

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        return raw_decorator(func)

    return decorator


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
def purge_old_s3_assets(retention_days: int | None = None) -> dict[str, Any]:
    """
    Scheduled task to purge S3 assets older than retention period.

    Args:
        retention_days: Days to retain; if None, uses GDPR result retention setting
    """
    try:
        settings = get_settings()
        exporter = GDPRDataExporter(settings)

        days = retention_days or settings.gdpr.result_retention_days
        result = asyncio.run(exporter.purge_old_assets(days))

        logger.info("s3_purge_task_completed", result=result)
        return result
    except Exception:
        logger.exception("s3_purge_task_failed")
        raise
