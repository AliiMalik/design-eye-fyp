"""LLM design-suggestion endpoints.

Suggestions are generated after the heatmap exists and are cached per result_id.
A slow or dead provider never blocks or invalidates the core analysis.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.core.deps import CurrentUser, DbDep, get_owned_asset
from app.core.errors import not_found
from app.db.mongo import Collections
from app.models.domain import LLMStatus, SuggestionDoc
from app.schemas.analysis import (
    SuggestionItemSchema,
    SuggestionsRequest,
    SuggestionsResponse,
)
from app.services.llm import generate_suggestions

logger = logging.getLogger(__name__)
router = APIRouter(tags=["suggestions"])


def _to_response(doc: dict) -> SuggestionsResponse:
    return SuggestionsResponse(
        result_id=doc["result_id"], summary=doc.get("summary", ""),
        suggestions=[SuggestionItemSchema(**i) for i in doc.get("items", [])],
        llm_status=doc.get("llm_status", "ok"), provider=doc.get("provider", ""),
        model_name=doc.get("model_name", ""), created_at=doc.get("created_at"),
    )


async def _rate_limited(db, user_id: str) -> bool:
    """Per-user daily cap, counted in Mongo."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db[Collections.LLM_USAGE].find_one_and_update(
        {"user_id": user_id, "day": day},
        {"$inc": {"count": 1}},
        upsert=True, return_document=True,
    )
    return int((doc or {}).get("count", 0)) > settings.LLM_RATE_LIMIT_PER_DAY


async def _load_result(db, asset_id: str, user_id: str) -> dict:
    await get_owned_asset(db, asset_id, user_id)
    result = await db[Collections.HEATMAP_RESULTS].find_one({"asset_id": asset_id},
                                                            {"_id": 0})
    if result is None:
        raise not_found("Result")
    return result


@router.get("/results/{asset_id}/suggestions", response_model=SuggestionsResponse)
async def get_suggestions(asset_id: str, user: CurrentUser,
                          db: DbDep) -> SuggestionsResponse:
    """Return cached suggestions, or an unavailable status if none exist yet."""
    result = await _load_result(db, asset_id, user["user_id"])
    cached = await db[Collections.SUGGESTIONS].find_one(
        {"result_id": result["result_id"]}, {"_id": 0})
    if cached:
        return _to_response(cached)
    return SuggestionsResponse(
        result_id=result["result_id"], llm_status=LLMStatus.UNAVAILABLE.value,
        provider=settings.LLM_PROVIDER,
    )


@router.post("/results/{asset_id}/suggestions", response_model=SuggestionsResponse)
async def create_suggestions(asset_id: str, payload: SuggestionsRequest,
                             user: CurrentUser, db: DbDep) -> SuggestionsResponse:
    """Generate suggestions, or return the cached set unless regenerate=true."""
    result = await _load_result(db, asset_id, user["user_id"])
    result_id = result["result_id"]

    cached = await db[Collections.SUGGESTIONS].find_one({"result_id": result_id},
                                                        {"_id": 0})
    if cached and not payload.regenerate:
        return _to_response(cached)

    if await _rate_limited(db, user["user_id"]):
        logger.info("LLM daily rate limit hit for user %s", user["user_id"])
        return SuggestionsResponse(
            result_id=result_id, llm_status=LLMStatus.RATE_LIMITED.value,
            provider=settings.LLM_PROVIDER,
            summary="Daily suggestion limit reached. Try again tomorrow.",
        )

    asset = await db[Collections.MOCKUP_ASSETS].find_one({"asset_id": asset_id},
                                                          {"_id": 0})
    analytics = {
        "clarity_score": result["clarity_score"],
        "focus_index": result.get("focus_index"),
        "clutter_index": result.get("clutter_index"),
        "focus_nodes": result.get("focus_nodes", []),
        "region_saliency": result.get("region_saliency", {}),
        "image_meta": {"width": (asset or {}).get("width", 0),
                       "height": (asset or {}).get("height", 0)},
    }

    payload_obj, status_str, provider, model_name = await generate_suggestions(
        analytics, payload.user_context)

    if payload_obj is None:
        return SuggestionsResponse(
            result_id=result_id, llm_status=status_str, provider=provider,
            model_name=model_name,
        )

    doc = SuggestionDoc(
        result_id=result_id, user_id=user["user_id"], provider=provider,
        model_name=model_name, summary=payload_obj.summary,
        items=[i.model_dump() for i in payload_obj.suggestions],
        llm_status=LLMStatus.OK,
    ).to_mongo()
    await db[Collections.SUGGESTIONS].replace_one({"result_id": result_id},
                                                  dict(doc), upsert=True)
    return _to_response(doc)
