"""Task status polling, result retrieval, rerun, delete, and PDF export."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response

from app.core.deps import (
    CurrentUser,
    DbDep,
    get_owned_asset,
    get_owned_task,
)
from app.core.errors import bad_request, not_found, server_error
from app.db.mongo import Collections
from app.schemas.analysis import (
    FocusNodeSchema,
    RerunResponse,
    ResultListItem,
    ResultListResponse,
    ResultResponse,
    ScanpathStep,
    StatusResponse,
    ViewportSchema,
)
from app.schemas.common import MessageResponse
from app.services.analytics import FocusNodeData, scanpath_timeline
from app.services.cleanup import purge_assets
from app.services.jobs import enqueue_analysis
from app.services.pdf import build_result_report
from app.services.scanpath import (
    FFmpegUnavailable,
    build_clip,
    encode_gif,
    encode_mp4,
    filmstrip,
)
from app.services.storage import get_storage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["results"])


def _scanpath_nodes(result: dict) -> list[dict]:
    """The animation sequence, falling back to focus_nodes for older documents."""
    nodes = result.get("scanpath_nodes") or result.get("focus_nodes") or []
    return list(nodes)


def _timeline(result: dict) -> list[dict]:
    nodes = [
        FocusNodeData(x=int(n["x"]), y=int(n["y"]), rank=int(n["rank"]),
                      intensity=float(n.get("intensity", 0.5)))
        for n in _scanpath_nodes(result)
    ]
    return scanpath_timeline(nodes) if nodes else []


def _result_response(asset: dict, result: dict) -> ResultResponse:
    timeline = _timeline(result)
    return ResultResponse(
        result_id=result["result_id"],
        asset_id=result["asset_id"],
        heatmap_url=result["heatmap_url"],
        saliency_array_url=result["saliency_array_url"],
        mockup_url=asset.get("file_url", ""),
        clarity_score=result["clarity_score"],
        focus_index=result.get("focus_index", 0.0),
        clutter_index=result.get("clutter_index", 0.0),
        region_saliency=result.get("region_saliency", {}),
        focus_nodes=[FocusNodeSchema(**n) for n in result.get("focus_nodes", [])],
        scanpath=[ScanpathStep(**step) for step in timeline],
        scanpath_total_ms=timeline[-1]["end_ms"] if timeline else 0,
        model_version=result["model_version"],
        inference_time_ms=result.get("inference_time_ms", 0),
        created_at=result["created_at"],
        image_width=asset.get("width", 0),
        image_height=asset.get("height", 0),
        original_filename=asset.get("original_filename", ""),
        project_id=asset.get("project_id", ""),
        viewport_device=result.get("viewport_device", ""),
        viewport_count=int(result.get("viewport_count", 1) or 1),
        viewports=[ViewportSchema(**v) for v in result.get("viewports", [])],
        weakest_viewport=result.get("weakest_viewport"),
        score_in_range=bool(result.get("score_in_range", True)),
        ui_theme=result.get("ui_theme", "light"),
    )


@router.get("/status/{task_id}", response_model=StatusResponse)
async def get_status(task_id: str, user: CurrentUser, db: DbDep) -> StatusResponse:
    """Poll an inference task. Another user's task returns 403."""
    task = await get_owned_task(db, task_id, user["user_id"])
    response = StatusResponse(
        task_id=task["task_id"], asset_id=task["asset_id"], status=task["status"],
        stage=task.get("stage", "queued"), error=task.get("error"),
        created_at=task["created_at"], completed_at=task.get("completed_at"),
    )

    if task["status"] == "complete":
        result = await db[Collections.HEATMAP_RESULTS].find_one(
            {"asset_id": task["asset_id"]}, {"_id": 0})
        if result:
            response.result_url = result["heatmap_url"]
            response.clarity_score = result["clarity_score"]
            response.focus_nodes = [FocusNodeSchema(**n)
                                    for n in result.get("focus_nodes", [])]
    return response


@router.get("/results", response_model=ResultListResponse)
async def list_results(user: CurrentUser, db: DbDep,
                       page: int = Query(1, ge=1),
                       limit: int = Query(20, ge=1, le=100),
                       project_id: str | None = Query(default=None)
                       ) -> ResultListResponse:
    """Paginated analysis history, scoped to the signed-in user."""
    query: dict = {"user_id": user["user_id"]}
    if project_id:
        query["project_id"] = project_id

    total = await db[Collections.MOCKUP_ASSETS].count_documents(query)
    cursor = (db[Collections.MOCKUP_ASSETS].find(query, {"_id": 0})
              .sort("uploaded_at", -1).skip((page - 1) * limit).limit(limit))
    assets = await cursor.to_list(length=limit)

    items: list[ResultListItem] = []
    for asset in assets:
        result = await db[Collections.HEATMAP_RESULTS].find_one(
            {"asset_id": asset["asset_id"]}, {"_id": 0})
        items.append(ResultListItem(
            asset_id=asset["asset_id"], project_id=asset["project_id"],
            original_filename=asset["original_filename"], status=asset["status"],
            uploaded_at=asset["uploaded_at"],
            clarity_score=(result or {}).get("clarity_score"),
            heatmap_url=(result or {}).get("heatmap_url"),
            mockup_url=asset.get("file_url"),
            width=asset.get("width", 0), height=asset.get("height", 0),
        ))

    return ResultListResponse(results=items, total_count=total, page=page, limit=limit)


@router.get("/results/{asset_id}", response_model=ResultResponse)
async def get_result(asset_id: str, user: CurrentUser, db: DbDep) -> ResultResponse:
    """Full analysis for one asset. Another user's asset returns 403 (TC-12)."""
    asset = await get_owned_asset(db, asset_id, user["user_id"])
    result = await db[Collections.HEATMAP_RESULTS].find_one({"asset_id": asset_id},
                                                            {"_id": 0})
    if result is None:
        raise not_found("Result")
    return _result_response(asset, result)


@router.post("/results/{asset_id}/rerun", response_model=RerunResponse)
async def rerun_analysis(asset_id: str, background: BackgroundTasks,
                         user: CurrentUser, db: DbDep) -> RerunResponse:
    """Re-analyse a stored asset without a fresh upload (TC-13)."""
    asset = await get_owned_asset(db, asset_id, user["user_id"])
    storage = get_storage()
    if not storage.exists(asset["storage_key"]):
        raise bad_request("The stored file for this asset is no longer available.")

    await db[Collections.MOCKUP_ASSETS].update_one(
        {"asset_id": asset_id}, {"$set": {"status": "pending"}})
    task_id = await enqueue_analysis(db, background, asset_id, user["user_id"])
    return RerunResponse(new_task_id=task_id, status="pending")


@router.delete("/results/{asset_id}", response_model=MessageResponse)
async def delete_result(asset_id: str, user: CurrentUser, db: DbDep) -> MessageResponse:
    """Delete an asset and its derived artefacts."""
    await get_owned_asset(db, asset_id, user["user_id"])
    await purge_assets(db, [asset_id])
    return MessageResponse(message="Analysis deleted")


@router.get("/results/{asset_id}/report.pdf")
async def download_report(asset_id: str, user: CurrentUser, db: DbDep) -> Response:
    """Generate the single-result PDF report."""
    asset = await get_owned_asset(db, asset_id, user["user_id"])
    result = await db[Collections.HEATMAP_RESULTS].find_one({"asset_id": asset_id},
                                                            {"_id": 0})
    if result is None:
        raise not_found("Result")

    storage = get_storage()
    heatmap_png: bytes | None = None
    try:
        key = (result.get("storage_keys") or {}).get("heatmap")
        if key:
            heatmap_png = storage.read_bytes(key)
    except Exception as exc:  # noqa: BLE001 - report still renders without it
        logger.warning("Could not read heatmap for the PDF: %s", exc)

    project = await db[Collections.PROJECTS].find_one(
        {"project_id": asset.get("project_id")}, {"_id": 0, "title": 1})
    suggestions = await db[Collections.SUGGESTIONS].find_one(
        {"result_id": result["result_id"]}, {"_id": 0})

    # A PDF cannot animate, so the replay becomes a contact sheet. Failing to
    # build it must not cost the reader the rest of the report.
    strip: bytes | None = None
    try:
        _, clip = await _scanpath_clip(asset_id, user["user_id"], db)
        strip = filmstrip(clip, columns=2, rows=3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not build the scanpath filmstrip: %s", exc)

    try:
        pdf = build_result_report(asset, result, heatmap_png, suggestions,
                                  (project or {}).get("title", ""), strip)
    except Exception as exc:  # noqa: BLE001
        raise server_error("PDF generation failed", exc) from exc

    filename = f"designeye-{asset.get('original_filename', 'report')}.pdf".replace(" ", "-")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _scanpath_clip(asset_id: str, user_id: str, db):
    """Load the mockup and render the playback frames. Shared by both formats."""
    asset = await get_owned_asset(db, asset_id, user_id)
    result = await db[Collections.HEATMAP_RESULTS].find_one({"asset_id": asset_id},
                                                            {"_id": 0})
    if result is None:
        raise not_found("Result")

    nodes = _scanpath_nodes(result)
    if not nodes:
        raise bad_request("This analysis has no focus points to play back.")

    storage = get_storage()
    try:
        raw = storage.read_bytes(asset["storage_key"])
    except Exception as exc:  # noqa: BLE001
        raise bad_request("The stored image for this analysis is unavailable.") from exc

    import io as _io

    from PIL import Image as _Image

    image = _Image.open(_io.BytesIO(raw))
    image.load()
    return asset, build_clip(image.convert("RGB"), nodes)


def _download_name(asset: dict, suffix: str) -> str:
    stem = (asset.get("original_filename") or "scanpath").rsplit(".", 1)[0]
    return f"designeye-scanpath-{stem}.{suffix}".replace(" ", "-")


@router.get("/results/{asset_id}/scanpath.gif")
async def download_scanpath_gif(asset_id: str, user: CurrentUser,
                                db: DbDep) -> Response:
    """Looping animated GIF of the predicted viewing order."""
    asset, clip = await _scanpath_clip(asset_id, user["user_id"], db)
    try:
        payload = encode_gif(clip)
    except Exception as exc:  # noqa: BLE001
        raise server_error("Scanpath GIF encoding failed", exc) from exc

    return Response(
        content=payload, media_type="image/gif",
        headers={"Content-Disposition":
                 f'attachment; filename="{_download_name(asset, "gif")}"'},
    )


@router.get("/results/{asset_id}/scanpath.mp4")
async def download_scanpath_mp4(asset_id: str, user: CurrentUser,
                                db: DbDep) -> Response:
    """H.264 MP4 of the same playback. Requires ffmpeg on the server."""
    asset, clip = await _scanpath_clip(asset_id, user["user_id"], db)
    try:
        payload = encode_mp4(clip)
    except FFmpegUnavailable as exc:
        # A missing encoder is a server capability gap, not a client mistake.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise server_error("Scanpath MP4 encoding failed", exc) from exc

    return Response(
        content=payload, media_type="video/mp4",
        headers={"Content-Disposition":
                 f'attachment; filename="{_download_name(asset, "mp4")}"'},
    )
