"""Index creation, run once at application startup."""

from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.db.mongo import Collections

logger = logging.getLogger(__name__)


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create every index the SDS schema and BUILD.md section 7 require."""
    await db[Collections.USERS].create_index([("email", ASCENDING)], unique=True)
    await db[Collections.USERS].create_index([("user_id", ASCENDING)], unique=True)

    await db[Collections.PROJECTS].create_index([("user_id", ASCENDING)])
    await db[Collections.PROJECTS].create_index([("project_id", ASCENDING)], unique=True)
    await db[Collections.PROJECTS].create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)])

    await db[Collections.MOCKUP_ASSETS].create_index([("project_id", ASCENDING)])
    await db[Collections.MOCKUP_ASSETS].create_index([("user_id", ASCENDING)])
    await db[Collections.MOCKUP_ASSETS].create_index([("asset_id", ASCENDING)], unique=True)
    await db[Collections.MOCKUP_ASSETS].create_index(
        [("user_id", ASCENDING), ("uploaded_at", DESCENDING)])

    await db[Collections.MOCKUP_ASSETS].create_index([("batch_id", ASCENDING)])

    await db[Collections.BATCHES].create_index([("batch_id", ASCENDING)], unique=True)
    await db[Collections.BATCHES].create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)])

    await db[Collections.HEATMAP_RESULTS].create_index([("asset_id", ASCENDING)], unique=True)
    await db[Collections.HEATMAP_RESULTS].create_index([("result_id", ASCENDING)], unique=True)
    await db[Collections.HEATMAP_RESULTS].create_index([("user_id", ASCENDING)])

    await db[Collections.AB_COMPARISONS].create_index([("comparison_id", ASCENDING)], unique=True)
    await db[Collections.AB_COMPARISONS].create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)])

    await db[Collections.INFERENCE_TASKS].create_index([("task_id", ASCENDING)], unique=True)
    await db[Collections.INFERENCE_TASKS].create_index([("asset_id", ASCENDING)])
    await db[Collections.INFERENCE_TASKS].create_index([("user_id", ASCENDING)])

    await db[Collections.SUGGESTIONS].create_index([("result_id", ASCENDING)], unique=True)
    await db[Collections.SUGGESTIONS].create_index([("suggestion_id", ASCENDING)], unique=True)

    # Revoked refresh tokens self-expire when the token itself would have.
    await db[Collections.REFRESH_DENYLIST].create_index([("jti", ASCENDING)], unique=True)
    await db[Collections.REFRESH_DENYLIST].create_index(
        [("expires_at", ASCENDING)], expireAfterSeconds=0)

    await db[Collections.LLM_USAGE].create_index(
        [("user_id", ASCENDING), ("day", ASCENDING)], unique=True)

    logger.info("MongoDB indexes ensured")
