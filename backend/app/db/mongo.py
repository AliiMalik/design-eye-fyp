"""Async MongoDB connection management (Motor)."""

from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


class Collections:
    USERS = "users"
    PROJECTS = "projects"
    MOCKUP_ASSETS = "mockup_assets"
    HEATMAP_RESULTS = "heatmap_results"
    AB_COMPARISONS = "ab_comparisons"
    INFERENCE_TASKS = "inference_tasks"
    SUGGESTIONS = "suggestions"
    REFRESH_DENYLIST = "refresh_denylist"
    LLM_USAGE = "llm_usage"


async def connect_to_mongo() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is not None:
        return _db
    _client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
    _db = _client[settings.MONGODB_DB]
    logger.info("Connected to MongoDB db=%s", settings.MONGODB_DB)
    return _db


async def close_mongo_connection() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
        _client, _db = None, None
        logger.info("Closed MongoDB connection")


def get_database() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialised; call connect_to_mongo() first.")
    return _db


async def ping() -> bool:
    """True when the database answers a ping; used by /health."""
    try:
        if _db is None:
            return False
        await _db.command("ping")
        return True
    except Exception:  # noqa: BLE001 - health check must never raise
        return False
