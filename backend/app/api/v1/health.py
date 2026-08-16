"""Health probe. Unauthenticated by design so orchestrators can call it."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.config import settings
from app.db.mongo import ping as db_ping
from app.ml.inference import get_model_meta, is_loaded
from app.schemas.common import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


def _redis_ok() -> bool:
    """True when the broker answers. DEV_MODE does not need Redis at all."""
    try:
        import redis

        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        return bool(client.ping())
    except Exception:  # noqa: BLE001 - health must never raise
        return False


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_ok = await db_ping()
    model_ok = is_loaded()
    redis_ok = _redis_ok()

    # In DEV_MODE inference runs inline, so Redis is not required to be healthy.
    healthy = db_ok and model_ok and (redis_ok or settings.DEV_MODE)

    meta = get_model_meta()
    return HealthResponse(
        status="ok" if healthy else "degraded",
        model_loaded=model_ok,
        db=db_ok,
        redis=redis_ok,
        version=settings.APP_VERSION,
        dev_mode=settings.DEV_MODE,
        model_info={
            "model_version": settings.MODEL_VERSION,
            "checkpoint_version": meta.get("checkpoint_model_version"),
            "epoch": meta.get("epoch"),
            "device": meta.get("device"),
            "val_metrics": meta.get("val"),
        },
    )
