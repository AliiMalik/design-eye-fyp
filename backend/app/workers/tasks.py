"""Celery tasks.

Each task opens its own Motor client inside a fresh event loop: a Motor client
is bound to the loop that created it, so the API's client cannot be reused here.
"""

from __future__ import annotations

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.services.pipeline import run_inference_pipeline
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run(task_id: str, asset_id: str, user_id: str) -> str | None:
    client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
    try:
        db = client[settings.MONGODB_DB]
        return await run_inference_pipeline(db, task_id, asset_id, user_id)
    finally:
        client.close()


@celery_app.task(name="designeye.run_inference", bind=True, max_retries=1)
def run_inference_task(self, task_id: str, asset_id: str, user_id: str) -> dict:
    """Analyse one uploaded mockup."""
    logger.info("Celery picked up task=%s asset=%s", task_id, asset_id)
    result_id = asyncio.run(_run(task_id, asset_id, user_id))
    return {"task_id": task_id, "asset_id": asset_id, "result_id": result_id,
            "status": "complete" if result_id else "failed"}
