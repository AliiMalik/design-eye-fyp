"""Multi-screen uploads: one PDF fanned out into N analysed screens.

A Figma "export frames to PDF" carries a whole flow. Each page becomes its own
MockupAsset so the existing single-screen machinery -- results, rerun, scanpath,
PDF, tenant isolation -- applies unchanged. The batch document only groups them
and holds the flow-level LLM output.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, Response, UploadFile, status

from app.core.deps import CurrentUser, DbDep, get_owned_project, owned_or_403
from app.core.errors import bad_request, server_error
from app.db.mongo import Collections
from app.models.domain import (
    AssetFormat,
    AssetStatus,
    BatchStatus,
    LLMStatus,
    MockupAsset,
    Project,
    ScreenBatch,
    SuggestionDoc,
)
from app.schemas.analysis import (
    BatchListItem,
    BatchListResponse,
    BatchResponse,
    BatchScreen,
    BatchSuggestionsRequest,
    BatchUploadResponse,
    SuggestionItemSchema,
)
from app.schemas.common import MessageResponse
from app.services.images import (
    MAX_PDF_PAGES,
    UnsupportedFileError,
    count_pdf_pages,
    encode_png,
    load_pdf_pages,
    sniff_format,
    validate_size,
)
from app.services.jobs import enqueue_analysis
from app.services.llm import generate_flow_suggestions
from app.services.pdf import build_flow_report
from app.services.quota import consume_llm_quota
from app.services.storage import get_storage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["batches"])


def _derive_status(total: int, complete: int, failed: int) -> str:
    """Status is derived, never stored.

    A crashed worker would otherwise leave a batch reading "processing" forever.
    Both the list and the detail view call this, so they cannot disagree.
    """
    if total == 0:
        return BatchStatus.PROCESSING.value
    if complete == total:
        return BatchStatus.COMPLETE.value
    if failed == total:
        return BatchStatus.FAILED.value
    if complete + failed == total:
        return BatchStatus.PARTIAL.value
    return BatchStatus.PROCESSING.value


async def get_owned_batch(db, batch_id: str, user_id: str) -> dict:
    return await owned_or_403(db, Collections.BATCHES, "batch_id", batch_id,
                              user_id, "Batch")


@router.post("/upload/batch", response_model=BatchUploadResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def upload_batch(
    background: BackgroundTasks,
    user: CurrentUser,
    db: DbDep,
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    project_title: str | None = Form(default=None),
) -> BatchUploadResponse:
    """Accept a multi-page PDF and queue every screen for analysis.

    Returns 202 with one task per screen. The frontend polls the batch for
    aggregate progress rather than each task individually.
    """
    raw = await file.read()

    try:
        fmt = sniff_format(raw)
    except UnsupportedFileError as exc:
        raise bad_request(str(exc)) from exc

    if fmt != AssetFormat.PDF:
        raise bad_request(
            "Batch analysis expects a multi-page PDF. Upload single images "
            "through the normal upload instead."
        )

    # Before counting: a rejected upload should never be parsed first.
    try:
        validate_size(raw, fmt)
    except UnsupportedFileError as exc:
        raise bad_request(str(exc)) from exc

    detected = count_pdf_pages(raw)
    try:
        pages = load_pdf_pages(raw)
    except UnsupportedFileError as exc:
        raise bad_request(str(exc)) from exc

    if len(pages) < 2:
        raise bad_request(
            "This PDF has only one screen. Use the normal upload for a single "
            "design."
        )

    # Group the screens under a project so the existing history views work.
    source_name = (file.filename or "flow.pdf")[:255]
    if project_id:
        await get_owned_project(db, project_id, user["user_id"])
    else:
        title = (project_title or source_name.rsplit(".", 1)[0])[:160]
        project = Project(user_id=user["user_id"], title=title,
                          description=f"{len(pages)} screens from {source_name}")
        await db[Collections.PROJECTS].insert_one(dict(project.to_mongo()))
        project_id = project.project_id

    batch = ScreenBatch(
        user_id=user["user_id"], project_id=project_id,
        source_filename=source_name, page_count=len(pages),
        pages_skipped=max(0, detected - len(pages)),
    )
    await db[Collections.BATCHES].insert_one(dict(batch.to_mongo()))

    storage = get_storage()
    task_ids: list[str] = []

    for index, page in enumerate(pages, start=1):
        asset = MockupAsset(
            project_id=project_id, user_id=user["user_id"], file_url="",
            storage_key="", original_filename=f"{source_name} screen {index}",
            format=AssetFormat.PNG, file_size_kb=max(1, len(raw) // 1024 // len(pages)),
            width=page.width, height=page.height, status=AssetStatus.PENDING,
            batch_id=batch.batch_id, page_number=index,
        )
        key = storage.tenant_key(user["user_id"], "uploads", f"{asset.asset_id}.png")
        try:
            asset.file_url = storage.save_bytes(key, encode_png(page), "image/png")
            asset.storage_key = key
        except Exception as exc:  # noqa: BLE001
            raise server_error("Failed to persist a batch screen", exc) from exc

        await db[Collections.MOCKUP_ASSETS].insert_one(dict(asset.to_mongo()))
        task_ids.append(
            await enqueue_analysis(db, background, asset.asset_id, user["user_id"])
        )

    logger.info("Batch %s accepted: %d screens from %s (skipped %d)",
                batch.batch_id, len(pages), source_name, batch.pages_skipped)

    return BatchUploadResponse(
        batch_id=batch.batch_id, project_id=project_id, page_count=len(pages),
        pages_skipped=batch.pages_skipped, task_ids=task_ids,
    )


async def _assemble(db, batch: dict) -> BatchResponse:
    """Join the batch with its screens, their results, and cached suggestions."""
    cursor = (db[Collections.MOCKUP_ASSETS]
              .find({"batch_id": batch["batch_id"]}, {"_id": 0})
              .sort("page_number", 1))
    assets = await cursor.to_list(length=MAX_PDF_PAGES)

    screens: list[BatchScreen] = []
    scores: list[float] = []
    complete = failed = 0

    for asset in assets:
        result = await db[Collections.HEATMAP_RESULTS].find_one(
            {"asset_id": asset["asset_id"]}, {"_id": 0})

        suggestions: list[SuggestionItemSchema] = []
        headline = ""
        if result:
            cached = await db[Collections.SUGGESTIONS].find_one(
                {"result_id": result["result_id"]}, {"_id": 0})
            if cached:
                suggestions = [SuggestionItemSchema(**i) for i in cached.get("items", [])]
                headline = cached.get("summary", "")

        if asset["status"] == AssetStatus.COMPLETE.value:
            complete += 1
        elif asset["status"] == AssetStatus.FAILED.value:
            failed += 1
        if result:
            scores.append(float(result["clarity_score"]))

        screens.append(BatchScreen(
            asset_id=asset["asset_id"],
            page_number=asset.get("page_number") or 0,
            original_filename=asset["original_filename"],
            status=asset["status"],
            mockup_url=asset.get("file_url", ""),
            heatmap_url=(result or {}).get("heatmap_url"),
            clarity_score=(result or {}).get("clarity_score"),
            focus_index=(result or {}).get("focus_index"),
            clutter_index=(result or {}).get("clutter_index"),
            width=asset.get("width", 0), height=asset.get("height", 0),
            suggestions=suggestions, headline=headline,
        ))

    derived = _derive_status(len(assets), complete, failed)

    return BatchResponse(
        batch_id=batch["batch_id"], project_id=batch["project_id"],
        source_filename=batch["source_filename"], page_count=batch["page_count"],
        pages_skipped=batch.get("pages_skipped", 0), status=derived,
        created_at=batch["created_at"], screens=screens,
        screens_complete=complete, screens_failed=failed,
        avg_clarity_score=round(sum(scores) / len(scores), 2) if scores else None,
        weakest_screen=batch.get("weakest_screen"),
        strongest_screen=batch.get("strongest_screen"),
        flow_summary=batch.get("flow_summary", ""),
        llm_status=batch.get("llm_status"),
        llm_provider=batch.get("llm_provider", ""),
        llm_model=batch.get("llm_model", ""),
    )


@router.get("/batches", response_model=BatchListResponse)
async def list_batches(user: CurrentUser, db: DbDep,
                       page: int = Query(1, ge=1),
                       limit: int = Query(20, ge=1, le=100)) -> BatchListResponse:
    query = {"user_id": user["user_id"]}
    total = await db[Collections.BATCHES].count_documents(query)
    cursor = (db[Collections.BATCHES].find(query, {"_id": 0})
              .sort("created_at", -1).skip((page - 1) * limit).limit(limit))
    docs = await cursor.to_list(length=limit)

    # One aggregation for the whole page: per-batch progress and average score.
    # Reading the stored status here showed finished flows as "processing".
    ids = [d["batch_id"] for d in docs]
    rollup: dict[str, dict] = {}
    if ids:
        pipeline = [
            {"$match": {"batch_id": {"$in": ids}}},
            {"$lookup": {
                "from": Collections.HEATMAP_RESULTS, "localField": "asset_id",
                "foreignField": "asset_id", "as": "result",
            }},
            {"$group": {
                "_id": "$batch_id",
                "total": {"$sum": 1},
                "complete": {"$sum": {"$cond": [
                    {"$eq": ["$status", AssetStatus.COMPLETE.value]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [
                    {"$eq": ["$status", AssetStatus.FAILED.value]}, 1, 0]}},
                "avg": {"$avg": {"$arrayElemAt": ["$result.clarity_score", 0]}},
            }},
        ]
        async for row in db[Collections.MOCKUP_ASSETS].aggregate(pipeline):
            rollup[row["_id"]] = row

    items: list[BatchListItem] = []
    for doc in docs:
        row = rollup.get(doc["batch_id"], {})
        avg = row.get("avg")
        items.append(BatchListItem(
            batch_id=doc["batch_id"], project_id=doc["project_id"],
            source_filename=doc["source_filename"], page_count=doc["page_count"],
            status=_derive_status(int(row.get("total", 0)),
                                  int(row.get("complete", 0)),
                                  int(row.get("failed", 0))),
            created_at=doc["created_at"],
            avg_clarity_score=round(float(avg), 2) if avg is not None else None,
        ))

    return BatchListResponse(batches=items, total_count=total, page=page, limit=limit)


@router.get("/batches/{batch_id}", response_model=BatchResponse)
async def get_batch(batch_id: str, user: CurrentUser, db: DbDep) -> BatchResponse:
    """Batch detail with every screen. Another user's batch returns 403."""
    batch = await get_owned_batch(db, batch_id, user["user_id"])
    return await _assemble(db, batch)


@router.delete("/batches/{batch_id}", response_model=MessageResponse)
async def delete_batch(batch_id: str, user: CurrentUser, db: DbDep) -> MessageResponse:
    """Delete a batch and every screen derived from it."""
    await get_owned_batch(db, batch_id, user["user_id"])

    assets = await db[Collections.MOCKUP_ASSETS].find(
        {"batch_id": batch_id}, {"_id": 0, "asset_id": 1, "storage_key": 1}
    ).to_list(length=MAX_PDF_PAGES)
    asset_ids = [a["asset_id"] for a in assets]

    storage = get_storage()
    results = await db[Collections.HEATMAP_RESULTS].find(
        {"asset_id": {"$in": asset_ids}}, {"_id": 0}).to_list(length=MAX_PDF_PAGES)

    for key in [a.get("storage_key") for a in assets]:
        if key:
            try:
                storage.delete(key)
            except Exception as exc:  # noqa: BLE001 - DB cleanup still proceeds
                logger.warning("Could not delete %s: %s", key, exc)
    for result in results:
        for key in (result.get("storage_keys") or {}).values():
            try:
                storage.delete(key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not delete %s: %s", key, exc)
        await db[Collections.SUGGESTIONS].delete_many({"result_id": result["result_id"]})

    await db[Collections.HEATMAP_RESULTS].delete_many({"asset_id": {"$in": asset_ids}})
    await db[Collections.INFERENCE_TASKS].delete_many({"asset_id": {"$in": asset_ids}})
    await db[Collections.MOCKUP_ASSETS].delete_many({"batch_id": batch_id})
    await db[Collections.BATCHES].delete_one({"batch_id": batch_id})

    return MessageResponse(message="Batch deleted")


@router.post("/batches/{batch_id}/suggestions", response_model=BatchResponse)
async def generate_batch_suggestions(
    batch_id: str, payload: BatchSuggestionsRequest,
    user: CurrentUser, db: DbDep,
) -> BatchResponse:
    """Review every screen of the flow in ONE provider call.

    One call per screen would exhaust the daily quota in two uploads and could
    not compare screens, because each call would only ever see its own numbers.
    The single reply is fanned out into one suggestions document per screen, so
    GET /results/{asset_id}/suggestions keeps working untouched, plus the
    flow-level summary stored on the batch.
    """
    batch = await get_owned_batch(db, batch_id, user["user_id"])

    if batch.get("flow_summary") and not payload.regenerate:
        return await _assemble(db, batch)

    assets = await (db[Collections.MOCKUP_ASSETS]
                    .find({"batch_id": batch_id}, {"_id": 0})
                    .sort("page_number", 1)).to_list(length=MAX_PDF_PAGES)

    screens: list[dict] = []
    by_screen: dict[int, dict] = {}
    for asset in assets:
        result = await db[Collections.HEATMAP_RESULTS].find_one(
            {"asset_id": asset["asset_id"]}, {"_id": 0})
        if result is None:
            continue  # still processing or failed; review what is ready
        number = asset.get("page_number") or (len(screens) + 1)
        screens.append({
            "screen": number,
            "clarity_score": result["clarity_score"],
            "focus_index": result.get("focus_index"),
            "clutter_index": result.get("clutter_index"),
            "focus_nodes": result.get("focus_nodes", []),
            "region_saliency": result.get("region_saliency", {}),
        })
        by_screen[number] = {"asset": asset, "result": result}

    if not screens:
        raise bad_request("No screens have finished analysis yet.")

    # A whole flow is ONE unit: it is one provider call.
    if await consume_llm_quota(db, user["user_id"]):
        logger.info("LLM daily limit reached for user %s", user["user_id"])
        await db[Collections.BATCHES].update_one(
            {"batch_id": batch_id},
            {"$set": {"llm_status": LLMStatus.RATE_LIMITED.value}})
        return await _assemble(db, await get_owned_batch(db, batch_id, user["user_id"]))

    flow, status_str, provider, model_name = await generate_flow_suggestions(
        screens, payload.user_context)

    if flow is None:
        await db[Collections.BATCHES].update_one(
            {"batch_id": batch_id},
            {"$set": {"llm_status": status_str, "llm_provider": provider,
                      "llm_model": model_name}})
        return await _assemble(db, await get_owned_batch(db, batch_id, user["user_id"]))

    # Fan the one reply out to per-screen documents.
    for screen in flow.screens:
        entry = by_screen.get(screen.screen)
        if entry is None:
            continue
        doc = SuggestionDoc(
            result_id=entry["result"]["result_id"], user_id=user["user_id"],
            provider=provider, model_name=model_name,
            summary=screen.headline,
            items=[i.model_dump() for i in screen.suggestions],
            llm_status=LLMStatus.OK,
        ).to_mongo()
        await db[Collections.SUGGESTIONS].replace_one(
            {"result_id": entry["result"]["result_id"]}, dict(doc), upsert=True)

    await db[Collections.BATCHES].update_one(
        {"batch_id": batch_id},
        {"$set": {
            "flow_summary": flow.flow_summary,
            "weakest_screen": flow.weakest_screen,
            "strongest_screen": flow.strongest_screen,
            "llm_status": LLMStatus.OK.value,
            "llm_provider": provider,
            "llm_model": model_name,
        }},
    )
    logger.info("Batch %s reviewed in one call: %d screens, provider=%s",
                batch_id, len(flow.screens), provider)

    return await _assemble(db, await get_owned_batch(db, batch_id, user["user_id"]))


@router.get("/batches/{batch_id}/report.pdf")
async def download_flow_report(batch_id: str, user: CurrentUser, db: DbDep) -> Response:
    """One PDF covering the whole flow: summary, clarity table, page per screen."""
    batch = await get_owned_batch(db, batch_id, user["user_id"])
    assembled = await _assemble(db, batch)

    storage = get_storage()
    heatmaps: dict[str, bytes] = {}
    for screen in assembled.screens:
        result = await db[Collections.HEATMAP_RESULTS].find_one(
            {"asset_id": screen.asset_id}, {"_id": 0})
        key = ((result or {}).get("storage_keys") or {}).get("heatmap")
        if not key:
            continue
        try:
            heatmaps[screen.asset_id] = storage.read_bytes(key)
        except Exception as exc:  # noqa: BLE001 - report renders without it
            logger.warning("Could not read heatmap for %s: %s", screen.asset_id, exc)

    payload = {
        "source_filename": assembled.source_filename,
        "flow_summary": assembled.flow_summary,
        "weakest_screen": assembled.weakest_screen,
        "strongest_screen": assembled.strongest_screen,
    }
    screens = [s.model_dump() for s in assembled.screens]

    try:
        pdf = build_flow_report(payload, screens, heatmaps)
    except Exception as exc:  # noqa: BLE001
        raise server_error("Flow PDF generation failed", exc) from exc

    name = assembled.source_filename.rsplit(".", 1)[0].replace(" ", "-")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="designeye-flow-{name}.pdf"'},
    )

