"""Inference orchestration: image -> saliency -> analytics -> persisted result.

Runs identically under Celery and under the DEV_MODE BackgroundTasks fallback.
The stage names it writes to ``inference_tasks.stage`` drive the staged progress
narrative in the UI.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np
from motor.motor_asyncio import AsyncIOMotorDatabase
from PIL import Image

from app.config import settings
from app.db.mongo import Collections
from app.models.domain import (
    AssetStatus,
    HeatmapResult,
    TaskStatus,
    new_id,
)
from app.ml.inference import load_model, predict_saliency
from app.services.analytics import analyse
from app.services.storage import StorageService, get_storage

logger = logging.getLogger(__name__)

STAGE_PREPROCESSING = "preprocessing"
STAGE_INFERENCE = "running_inference"
STAGE_ANALYTICS = "computing_analytics"
STAGE_PERSISTING = "persisting"
STAGE_COMPLETE = "complete"


async def _set_stage(db: AsyncIOMotorDatabase, task_id: str, stage: str,
                     status: TaskStatus | None = None) -> None:
    update: dict[str, Any] = {"stage": stage}
    if status is not None:
        update["status"] = status.value
    await db[Collections.INFERENCE_TASKS].update_one(
        {"task_id": task_id}, {"$set": update})


def _encode_png(bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("Failed to encode the heatmap overlay as PNG")
    return buf.tobytes()


async def run_inference_pipeline(db: AsyncIOMotorDatabase, task_id: str,
                                 asset_id: str, user_id: str,
                                 storage: StorageService | None = None) -> str | None:
    """Execute the full analysis for one asset. Returns the result_id, or None.

    Never raises: any failure is recorded on the task and the asset so the
    frontend poll surfaces a clean error instead of hanging.
    """
    storage = storage or get_storage()
    assets = db[Collections.MOCKUP_ASSETS]
    tasks = db[Collections.INFERENCE_TASKS]

    try:
        await _set_stage(db, task_id, STAGE_PREPROCESSING, TaskStatus.PROCESSING)
        await assets.update_one({"asset_id": asset_id},
                                {"$set": {"status": AssetStatus.PROCESSING.value}})

        asset = await assets.find_one({"asset_id": asset_id}, {"_id": 0})
        if asset is None:
            raise FileNotFoundError(f"Asset {asset_id} no longer exists")

        raw = storage.read_bytes(asset["storage_key"])
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = img.convert("RGB")

        # --- inference ---------------------------------------------------
        await _set_stage(db, task_id, STAGE_INFERENCE)
        load_model(settings.MODEL_PATH)
        out = predict_saliency(img)

        # --- analytics ---------------------------------------------------
        await _set_stage(db, task_id, STAGE_ANALYTICS)
        image_rgb = np.array(img, dtype=np.uint8)
        metrics = analyse(out.saliency, image_rgb)

        # --- persist artefacts -------------------------------------------
        await _set_stage(db, task_id, STAGE_PERSISTING)
        overlay_key = storage.tenant_key(user_id, "results", f"{asset_id}_heatmap.png")
        saliency_key = storage.tenant_key(user_id, "results", f"{asset_id}_saliency.npy")

        heatmap_url = storage.save_bytes(overlay_key, _encode_png(out.overlay_bgr), "image/png")
        saliency_url = storage.save_npy(saliency_key, out.saliency)

        result = HeatmapResult(
            result_id=new_id(),
            asset_id=asset_id,
            user_id=user_id,
            heatmap_url=heatmap_url,
            saliency_array_url=saliency_url,
            clarity_score=metrics.clarity_score,
            focus_index=metrics.focus_index,
            clutter_index=metrics.clutter_index,
            region_saliency=metrics.region_saliency,
            focus_nodes=[n.as_dict() for n in metrics.focus_nodes],
            model_version=settings.MODEL_VERSION,
            inference_time_ms=out.inference_time_ms,
        )
        doc = result.to_mongo()
        doc["storage_keys"] = {"heatmap": overlay_key, "saliency": saliency_key}

        # A rerun replaces the previous result for this asset (asset_id is unique).
        await db[Collections.HEATMAP_RESULTS].replace_one(
            {"asset_id": asset_id}, doc, upsert=True)

        await assets.update_one(
            {"asset_id": asset_id},
            {"$set": {"status": AssetStatus.COMPLETE.value,
                      "width": img.width, "height": img.height}},
        )
        await tasks.update_one(
            {"task_id": task_id},
            {"$set": {"status": TaskStatus.COMPLETE.value,
                      "stage": STAGE_COMPLETE,
                      "completed_at": datetime.now(timezone.utc)}},
        )
        logger.info("Analysis complete asset=%s clarity=%.2f in %dms",
                    asset_id, metrics.clarity_score, out.inference_time_ms)
        return result.result_id

    except Exception as exc:  # noqa: BLE001 - failures are recorded, not raised
        logger.error("Inference pipeline failed for asset=%s: %s", asset_id, exc,
                     exc_info=True)
        await tasks.update_one(
            {"task_id": task_id},
            {"$set": {"status": TaskStatus.FAILED.value,
                      "stage": "failed",
                      "error": "Analysis failed. Please try again.",
                      "completed_at": datetime.now(timezone.utc)}},
        )
        await assets.update_one({"asset_id": asset_id},
                                {"$set": {"status": AssetStatus.FAILED.value}})
        return None
