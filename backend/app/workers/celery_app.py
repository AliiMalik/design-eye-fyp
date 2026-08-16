"""Celery application and worker bootstrap.

With DEV_MODE=true the API runs inference inline via FastAPI BackgroundTasks
instead, so the whole stack works with no Redis running at all.
"""

from __future__ import annotations

import logging

from celery import Celery
from celery.signals import worker_process_init

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "designeye",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_max_tasks_per_child=50,
    broker_connection_retry_on_startup=True,
)


@worker_process_init.connect
def load_model_on_worker_start(**_kwargs) -> None:
    """Load the checkpoint once per worker process, never per task."""
    from app.ml.inference import load_model

    try:
        load_model(settings.MODEL_PATH)
        logger.info("Celery worker: saliency model loaded")
    except Exception as exc:  # noqa: BLE001 - log loudly, let tasks fail cleanly
        logger.error("Celery worker failed to load the model: %s", exc)
