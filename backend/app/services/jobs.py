"""Job dispatch: Celery when a broker is available, inline when DEV_MODE.

DEV_MODE=true keeps the whole product working with no Redis and no worker
process, which is what the FYP demo machine runs (BUILD.md section 2).
"""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.db.mongo import Collections
from app.models.domain import InferenceTask
from app.services.pipeline import run_inference_pipeline

logger = logging.getLogger(__name__)


async def enqueue_analysis(db: AsyncIOMotorDatabase, background: BackgroundTasks,
                           asset_id: str, user_id: str) -> str:
    """Create an InferenceTask and dispatch it. Returns the task_id."""
    task = InferenceTask(asset_id=asset_id, user_id=user_id)
    await db[Collections.INFERENCE_TASKS].insert_one(task.to_mongo())

    if settings.DEV_MODE:
        background.add_task(run_inference_pipeline, db, task.task_id, asset_id, user_id)
        logger.info("DEV_MODE: running task=%s inline", task.task_id)
        return task.task_id

    try:
        from app.workers.tasks import run_inference_task

        run_inference_task.delay(task.task_id, asset_id, user_id)
        logger.info("Queued task=%s to Celery", task.task_id)
    except Exception as exc:  # noqa: BLE001 - a dead broker must not lose the job
        logger.error("Celery dispatch failed (%s); running inline instead", exc)
        background.add_task(run_inference_pipeline, db, task.task_id, asset_id, user_id)

    return task.task_id
