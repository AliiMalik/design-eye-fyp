"""A/B comparison endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Response, status

from app.core.deps import (
    CurrentUser,
    DbDep,
    get_owned_asset,
    get_owned_comparison,
)
from app.core.errors import bad_request, not_found, server_error
from app.db.mongo import Collections
from app.models.domain import ABComparison
from app.schemas.analysis import (
    ComparisonListItem,
    ComparisonListResponse,
    ComparisonResponse,
    ComparisonSide,
    CompareRequest,
    FocusNodeSchema,
)
from app.schemas.common import MessageResponse
from app.services.pdf import build_comparison_report
from app.services.storage import get_storage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["compare"])


def _side(asset: dict, result: dict) -> ComparisonSide:
    return ComparisonSide(
        asset_id=asset["asset_id"],
        original_filename=asset.get("original_filename", ""),
        mockup_url=asset.get("file_url", ""),
        heatmap_url=result["heatmap_url"],
        clarity_score=result["clarity_score"],
        focus_index=result.get("focus_index", 0.0),
        clutter_index=result.get("clutter_index", 0.0),
        focus_nodes=[FocusNodeSchema(**n) for n in result.get("focus_nodes", [])],
        region_saliency=result.get("region_saliency", {}),
        width=asset.get("width", 0),
        height=asset.get("height", 0),
    )


async def _load_side(db, asset_id: str, user_id: str, label: str) -> tuple[dict, dict]:
    asset = await get_owned_asset(db, asset_id, user_id)
    result = await db[Collections.HEATMAP_RESULTS].find_one({"asset_id": asset_id},
                                                            {"_id": 0})
    if result is None:
        raise bad_request(f"{label} has not finished analysis yet.")
    return asset, result


@router.post("/compare", response_model=ComparisonResponse,
             status_code=status.HTTP_201_CREATED)
async def create_comparison(payload: CompareRequest, user: CurrentUser,
                            db: DbDep) -> ComparisonResponse:
    """Compare two analysed variants and persist the delta (TC-10)."""
    if payload.asset_id_a == payload.asset_id_b:
        raise bad_request("Choose two different designs to compare.")

    asset_a, result_a = await _load_side(db, payload.asset_id_a, user["user_id"], "Design A")
    asset_b, result_b = await _load_side(db, payload.asset_id_b, user["user_id"], "Design B")

    delta = round(float(result_a["clarity_score"]) - float(result_b["clarity_score"]), 2)
    comparison = ABComparison(
        user_id=user["user_id"], asset_id_a=payload.asset_id_a,
        asset_id_b=payload.asset_id_b, clarity_delta=delta,
    )
    doc = comparison.to_mongo()
    await db[Collections.AB_COMPARISONS].insert_one(dict(doc))

    return ComparisonResponse(
        comparison_id=comparison.comparison_id, clarity_delta=delta,
        winner="A" if delta > 0 else ("B" if delta < 0 else "tie"),
        design_a=_side(asset_a, result_a), design_b=_side(asset_b, result_b),
        created_at=comparison.created_at,
    )


@router.get("/compare", response_model=ComparisonListResponse)
async def list_comparisons(user: CurrentUser, db: DbDep,
                           page: int = Query(1, ge=1),
                           limit: int = Query(20, ge=1, le=100)
                           ) -> ComparisonListResponse:
    query = {"user_id": user["user_id"]}
    total = await db[Collections.AB_COMPARISONS].count_documents(query)
    cursor = (db[Collections.AB_COMPARISONS].find(query, {"_id": 0})
              .sort("created_at", -1).skip((page - 1) * limit).limit(limit))
    docs = await cursor.to_list(length=limit)
    return ComparisonListResponse(
        comparisons=[ComparisonListItem(**d) for d in docs],
        total_count=total, page=page, limit=limit,
    )


@router.get("/compare/{comparison_id}", response_model=ComparisonResponse)
async def get_comparison(comparison_id: str, user: CurrentUser,
                         db: DbDep) -> ComparisonResponse:
    comparison = await get_owned_comparison(db, comparison_id, user["user_id"])
    asset_a, result_a = await _load_side(db, comparison["asset_id_a"],
                                         user["user_id"], "Design A")
    asset_b, result_b = await _load_side(db, comparison["asset_id_b"],
                                         user["user_id"], "Design B")
    delta = float(comparison["clarity_delta"])
    return ComparisonResponse(
        comparison_id=comparison_id, clarity_delta=delta,
        winner="A" if delta > 0 else ("B" if delta < 0 else "tie"),
        design_a=_side(asset_a, result_a), design_b=_side(asset_b, result_b),
        created_at=comparison["created_at"],
    )


@router.delete("/compare/{comparison_id}", response_model=MessageResponse)
async def delete_comparison(comparison_id: str, user: CurrentUser,
                            db: DbDep) -> MessageResponse:
    await get_owned_comparison(db, comparison_id, user["user_id"])
    await db[Collections.AB_COMPARISONS].delete_one({"comparison_id": comparison_id})
    return MessageResponse(message="Comparison deleted")


@router.get("/compare/{comparison_id}/report.pdf")
async def download_comparison_report(comparison_id: str, user: CurrentUser,
                                     db: DbDep) -> Response:
    comparison = await get_owned_comparison(db, comparison_id, user["user_id"])
    asset_a, result_a = await _load_side(db, comparison["asset_id_a"],
                                         user["user_id"], "Design A")
    asset_b, result_b = await _load_side(db, comparison["asset_id_b"],
                                         user["user_id"], "Design B")

    storage = get_storage()

    def _heatmap(result: dict) -> bytes | None:
        key = (result.get("storage_keys") or {}).get("heatmap")
        if not key:
            return None
        try:
            return storage.read_bytes(key)
        except Exception as exc:  # noqa: BLE001 - report renders without it
            logger.warning("Could not read heatmap %s: %s", key, exc)
            return None

    try:
        pdf = build_comparison_report(
            comparison,
            {"asset": asset_a, "result": result_a},
            {"asset": asset_b, "result": result_b},
            _heatmap(result_a), _heatmap(result_b),
        )
    except Exception as exc:  # noqa: BLE001
        raise server_error("Comparison PDF generation failed", exc) from exc

    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="designeye-comparison-{comparison_id[:8]}.pdf"'},
    )
