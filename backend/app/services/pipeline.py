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
from app.ml.inference import build_overlay, load_model, predict_saliency_hires
from app.ml.theme import detect_theme, for_model, mean_luminance
from app.services.analytics import analyse
from app.services.storage import StorageService, get_storage
from app.services.viewports import (
    Viewport,
    ViewportScore,
    aggregate_scores,
    default_device,
    is_scoreable,
    slice_viewports,
    stitch_saliency,
)

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

        device = asset.get("viewport_device") or default_device(img.width, img.height)
        tiles = slice_viewports(img, device)
        image_rgb = np.array(img, dtype=np.uint8)

        # The checkpoint reads dark interfaces badly, so it is shown an inverted
        # copy. Detected once for the whole page rather than per viewport, so a
        # dark page cannot be scored under two different assumptions. Everything
        # not produced by the model still uses the original pixels.
        theme = detect_theme(img)
        dark = theme == "dark"
        if dark:
            logger.info("Asset %s looks dark-themed (luma %.0f); inverting for inference",
                        asset_id, mean_luminance(img))

        if len(tiles) == 1:
            out = predict_saliency_hires(for_model(img, dark))
            saliency = out.saliency
            # predict_saliency builds its overlay on whatever it was given, so on
            # the dark path that would be the inverted copy. The heatmap the user
            # sees must sit on the design they uploaded.
            overlay_bgr = build_overlay(img, saliency) if dark else out.overlay_bgr
            inference_ms = out.inference_time_ms
            per_viewport: list[ViewportScore] = []
        else:
            # A scrolling page is scored one screen at a time, because nobody
            # sees it all at once and the model cannot see it all at once
            # either. Segmenting BEFORE inference is the whole point: the
            # whole-page saliency map is derived from a sliver of the input, so
            # there is no signal in it left to partition afterwards.
            maps: list[tuple[Viewport, np.ndarray]] = []
            per_viewport = []
            inference_ms = 0
            for vp in tiles:
                vout = predict_saliency_hires(for_model(vp.image, dark))
                inference_ms += vout.inference_time_ms
                maps.append((vp, vout.saliency))
                vm = analyse(vout.saliency, np.array(vp.image, dtype=np.uint8))
                per_viewport.append(ViewportScore(
                    index=vp.index, top=vp.top, bottom=vp.bottom,
                    clarity_score=vm.clarity_score,
                    focus_index=vm.focus_index,
                    clutter_index=vm.clutter_index,
                ))
            saliency = stitch_saliency(maps, img.width, img.height)
            overlay_bgr = build_overlay(img, saliency)
            logger.info("Segmented %s into %d %s viewports", asset_id, len(tiles), device)

        # --- analytics ---------------------------------------------------
        await _set_stage(db, task_id, STAGE_ANALYTICS)
        # Focus Order, the replay and the region grid all come off the stitched
        # map, so their coordinates stay in the uploaded page's pixel space and
        # the numbered dots land where the user can see them.
        metrics = analyse(saliency, image_rgb)

        aggregate = aggregate_scores(per_viewport) if per_viewport else None
        if aggregate is not None:
            # The headline numbers are the per-viewport means. The whole-page
            # values that analyse() just computed are the broken ones.
            metrics.clarity_score = aggregate.clarity_score
            metrics.focus_index = aggregate.focus_index
            metrics.clutter_index = aggregate.clutter_index

        # Scoreability is a property of the frame's shape. A segmented page is
        # judged on its viewports; an unsegmentable shape (an ultra-wide export)
        # is judged on the whole frame and may simply be unscoreable.
        scoreable = (is_scoreable(tiles[0].image.width, tiles[0].image.height)
                     if per_viewport else is_scoreable(img.width, img.height))
        if not scoreable:
            logger.warning("Asset %s is %dx%d: too little signal after letterboxing",
                           asset_id, img.width, img.height)

        # --- persist artefacts -------------------------------------------
        await _set_stage(db, task_id, STAGE_PERSISTING)
        overlay_key = storage.tenant_key(user_id, "results", f"{asset_id}_heatmap.png")
        saliency_key = storage.tenant_key(user_id, "results", f"{asset_id}_saliency.npy")

        heatmap_url = storage.save_bytes(overlay_key, _encode_png(overlay_bgr), "image/png")
        saliency_url = storage.save_npy(saliency_key, saliency)

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
            scanpath_nodes=[n.as_dict() for n in metrics.scanpath_nodes],
            viewport_device=device if per_viewport else "",
            viewport_count=len(tiles),
            viewports=[v.as_dict() for v in per_viewport],
            weakest_viewport=aggregate.weakest_index if aggregate else None,
            score_in_range=scoreable,
            ui_theme=theme,
            model_version=settings.MODEL_VERSION,
            inference_time_ms=inference_ms,
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
        logger.info("Analysis complete asset=%s clarity=%.2f over %d viewport(s) in %dms",
                    asset_id, metrics.clarity_score, len(tiles), inference_ms)
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
