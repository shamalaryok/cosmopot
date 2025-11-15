from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

from celery import Celery, signals
from celery.schedules import crontab
from celery.utils.dispatch.signal import Signal

from .constants import TASK_NAMESPACE
from .worker.bootstrap import initialise, shutdown
from .worker.config import WorkerSettings
from .worker.logging import configure_logging

T = TypeVar("T", bound=Callable[..., Any])


def _connect_signal(signal: Signal, **connect_kwargs: Any) -> Callable[[T], T]:
    def decorator(func: T) -> T:
        signal.connect(func, **connect_kwargs)
        return func

    return decorator


_worker_settings = WorkerSettings()
configure_logging(_worker_settings.log_level)

celery_app = Celery(
    "generation_worker",
    broker=_worker_settings.celery_broker_url,
    backend=_worker_settings.celery_result_backend,
    include=[TASK_NAMESPACE],
)

celery_app.conf.update(
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_concurrency=4,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    task_default_queue="generation.tasks",
    task_default_delivery_mode="transient",
    worker_hijack_root_logger=False,
    beat_schedule={
        "purge-old-s3-assets": {
            "task": f"{TASK_NAMESPACE}.purge_old_s3_assets",
            "schedule": crontab(hour=1, minute=0),
            "kwargs": {},
        },
    },
)

celery_app.conf.task_routes = {
    f"{TASK_NAMESPACE}.process_generation_task": {"queue": "generation.tasks"},
    f"{TASK_NAMESPACE}.purge_old_s3_assets": {"queue": "generation.tasks"},
}


@_connect_signal(signals.worker_init)
def _on_worker_init(**_: object) -> None:
    asyncio.run(initialise())


@_connect_signal(signals.worker_shutdown)
def _on_worker_shutdown(**_: object) -> None:
    asyncio.run(shutdown())
