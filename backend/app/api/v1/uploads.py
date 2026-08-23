"""Upload endpoint. Returns 202 Accepted; the frontend polls /status/{task_id}."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile, status

from app.core.deps import CurrentUser, DbDep, get_owned_project
from app.core.errors import bad_request, server_error
from app.db.mongo import Collections
from app.models.domain import AssetFormat, AssetStatus, MockupAsset, Project
from app.schemas.analysis import UploadResponse
from app.services.images import (
    UnsupportedFileError,
    count_pdf_pages,
    encode_png,
    load_image,
)
from app.services.jobs import enqueue_analysis
from app.services.storage import get_storage
from app.services.viewports import VIEWPORT_ASPECTS, default_device

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])


@router.post("/upload", response_model=UploadResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def upload_mockup(
    background: BackgroundTasks,
    user: CurrentUser,
    db: DbDep,
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    project_title: str | None = Form(default=None),
    viewport_device: str | None = Form(default=None),
) -> UploadResponse:
    """Accept a mockup, store it, and queue analysis.

    Validation errors return 400 with a clear message (TC-04, TC-05); the
    format is sniffed from the bytes, never from the filename.
    """
    raw = await file.read()

    try:
        image, fmt = load_image(raw)
    except UnsupportedFileError as exc:
        raise bad_request(str(exc)) from exc

    # Which screen size a scrolling page is scored against. Stored on the
    # asset so a rerun reproduces the same segmentation.
    device = (viewport_device or "").strip().lower()
    if device and device not in VIEWPORT_ASPECTS:
        raise bad_request(
            f"Unknown screen size. Expected one of "
            f"{', '.join(sorted(VIEWPORT_ASPECTS))}."
        )
    device = device or default_device(image.width, image.height)

    # No project supplied: group by title instead, creating it on first use.
    #
    # The Chrome extension sends the captured site's hostname, so every capture
    # of one site collects in a project named after it rather than scattering
    # through a single bucket. Find-or-create rather than always-create, which
    # is what /upload/batch does -- a batch is one export and deserves its own
    # project, whereas captures accumulate.
    if project_id:
        await get_owned_project(db, project_id, user["user_id"])
    else:
        title = (project_title or "").strip()[:160] or "My Uploads"
        existing = await db[Collections.PROJECTS].find_one(
            {"user_id": user["user_id"], "title": title}, {"_id": 0})
        if existing:
            project_id = existing["project_id"]
        else:
            created = Project(
                user_id=user["user_id"],
                title=title,
                description=("Captured with the DesignEye Chrome extension"
                             if project_title else
                             "Mockups uploaded without a project"),
            )
            await db[Collections.PROJECTS].insert_one(dict(created.to_mongo()))
            project_id = created.project_id

    asset = MockupAsset(
        project_id=project_id,
        user_id=user["user_id"],
        file_url="",
        storage_key="",
        original_filename=(file.filename or "mockup")[:255],
        format=fmt,
        file_size_kb=max(1, len(raw) // 1024),
        width=image.width,
        height=image.height,
        status=AssetStatus.PENDING,
        viewport_device=device,
    )

    # Everything downstream reads a PNG, so SVG/PDF are persisted rasterised.
    storage = get_storage()
    key = storage.tenant_key(user["user_id"], "uploads", f"{asset.asset_id}.png")
    try:
        asset.file_url = storage.save_bytes(key, encode_png(image), "image/png")
        asset.storage_key = key
    except Exception as exc:  # noqa: BLE001
        raise server_error("Failed to persist upload", exc) from exc

    await db[Collections.MOCKUP_ASSETS].insert_one(dict(asset.to_mongo()))
    task_id = await enqueue_analysis(db, background, asset.asset_id, user["user_id"])

    # load_image() deliberately rasterises page 1 only. Report the true page
    # count so the client can offer batch analysis rather than the user being
    # told a 12-screen PDF is fully analysed.
    pages_detected = count_pdf_pages(raw) if fmt == AssetFormat.PDF else 1
    pages_detected = max(1, pages_detected)
    if pages_detected > 1:
        logger.info("Upload %s is a %d-page PDF; analysed page 1 only",
                    asset.asset_id, pages_detected)

    logger.info("Upload accepted asset=%s project=%s format=%s %dx%d",
                asset.asset_id, project_id, fmt.value, image.width, image.height)
    return UploadResponse(
        asset_id=asset.asset_id, task_id=task_id, status="pending",
        pages_detected=pages_detected, pages_analysed=1,
    )
