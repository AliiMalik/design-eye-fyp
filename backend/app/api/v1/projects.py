"""Project CRUD and the dashboard aggregate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbDep, get_owned_project
from app.db.mongo import Collections
from app.models.domain import Project, utcnow
from app.schemas.analysis import (
    AssetResponse,
    ClarityTrendPoint,
    DashboardStats,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
    ResultListItem,
)
from app.schemas.common import MessageResponse
from app.services.cleanup import purge_assets

router = APIRouter(tags=["projects"])


async def _decorate(db, project: dict) -> ProjectResponse:
    """Attach asset count and mean clarity to a project document."""
    asset_ids = await db[Collections.MOCKUP_ASSETS].distinct(
        "asset_id", {"project_id": project["project_id"]})
    avg = None
    if asset_ids:
        cursor = db[Collections.HEATMAP_RESULTS].aggregate([
            {"$match": {"asset_id": {"$in": asset_ids}}},
            {"$group": {"_id": None, "avg": {"$avg": "$clarity_score"}}},
        ])
        agg = await cursor.to_list(length=1)
        if agg:
            avg = round(float(agg[0]["avg"]), 2)

    return ProjectResponse(**{**project, "asset_count": len(asset_ids),
                              "avg_clarity_score": avg})


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(user: CurrentUser, db: DbDep,
                        page: int = Query(1, ge=1),
                        limit: int = Query(20, ge=1, le=100)) -> ProjectListResponse:
    """Paginated project history for the signed-in user only."""
    query = {"user_id": user["user_id"]}
    total = await db[Collections.PROJECTS].count_documents(query)
    cursor = (db[Collections.PROJECTS].find(query, {"_id": 0})
              .sort("created_at", -1).skip((page - 1) * limit).limit(limit))
    docs = await cursor.to_list(length=limit)
    return ProjectListResponse(
        projects=[await _decorate(db, d) for d in docs],
        total_count=total, page=page, limit=limit,
    )


@router.post("/projects", response_model=ProjectResponse,
             status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, user: CurrentUser,
                         db: DbDep) -> ProjectResponse:
    project = Project(user_id=user["user_id"], title=payload.title.strip(),
                      description=payload.description)
    doc = project.to_mongo()
    await db[Collections.PROJECTS].insert_one(dict(doc))
    return ProjectResponse(**doc, asset_count=0, avg_clarity_score=None)


@router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
async def get_project(project_id: str, user: CurrentUser,
                      db: DbDep) -> ProjectDetailResponse:
    """Project detail with its assets. Another user's project returns 403."""
    project = await get_owned_project(db, project_id, user["user_id"])
    cursor = (db[Collections.MOCKUP_ASSETS]
              .find({"project_id": project_id, "user_id": user["user_id"]}, {"_id": 0})
              .sort("uploaded_at", -1))
    assets = await cursor.to_list(length=500)
    return ProjectDetailResponse(
        project=await _decorate(db, project),
        assets=[AssetResponse(**a) for a in assets],
    )


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, payload: ProjectUpdate,
                         user: CurrentUser, db: DbDep) -> ProjectResponse:
    await get_owned_project(db, project_id, user["user_id"])
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if updates:
        updates["updated_at"] = utcnow()
        await db[Collections.PROJECTS].update_one({"project_id": project_id},
                                                  {"$set": updates})
    fresh = await db[Collections.PROJECTS].find_one({"project_id": project_id}, {"_id": 0})
    return await _decorate(db, fresh)


@router.delete("/projects/{project_id}", response_model=MessageResponse)
async def delete_project(project_id: str, user: CurrentUser,
                         db: DbDep) -> MessageResponse:
    """Delete a project and everything derived from it.

    Batches group screens by project, so a flow's grouping document has to go
    with it. Left behind it lists zero screens, and ``_derive_status`` reads a
    batch with no assets as "processing" -- which the batch view then polls
    forever, because only a settled status stops it.
    """
    await get_owned_project(db, project_id, user["user_id"])
    asset_ids = await db[Collections.MOCKUP_ASSETS].distinct(
        "asset_id", {"project_id": project_id})

    await purge_assets(db, asset_ids)
    await db[Collections.BATCHES].delete_many({"project_id": project_id})
    await db[Collections.PROJECTS].delete_one({"project_id": project_id})
    return MessageResponse(message="Project deleted")


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(user: CurrentUser, db: DbDep) -> DashboardStats:
    """Aggregate stats backing the dashboard cards and the clarity sparkline."""
    uid = user["user_id"]
    total_projects = await db[Collections.PROJECTS].count_documents({"user_id": uid})
    total_analyses = await db[Collections.HEATMAP_RESULTS].count_documents({"user_id": uid})

    month_start = datetime.now(timezone.utc) - timedelta(days=30)
    projects_this_month = await db[Collections.PROJECTS].count_documents(
        {"user_id": uid, "created_at": {"$gte": month_start}})

    avg_cursor = db[Collections.HEATMAP_RESULTS].aggregate([
        {"$match": {"user_id": uid}},
        {"$group": {"_id": None, "avg": {"$avg": "$clarity_score"}}},
    ])
    avg_docs = await avg_cursor.to_list(length=1)
    avg_clarity = round(float(avg_docs[0]["avg"]), 2) if avg_docs else 0.0

    trend_cursor = (db[Collections.HEATMAP_RESULTS]
                    .find({"user_id": uid},
                          {"_id": 0, "created_at": 1, "clarity_score": 1, "asset_id": 1})
                    .sort("created_at", -1).limit(12))
    trend_docs = await trend_cursor.to_list(length=12)

    trend: list[ClarityTrendPoint] = []
    for doc in reversed(trend_docs):
        asset = await db[Collections.MOCKUP_ASSETS].find_one(
            {"asset_id": doc["asset_id"]}, {"_id": 0, "original_filename": 1})
        trend.append(ClarityTrendPoint(
            date=doc["created_at"], clarity_score=doc["clarity_score"],
            asset_id=doc["asset_id"],
            original_filename=(asset or {}).get("original_filename", ""),
        ))

    recent_cursor = (db[Collections.MOCKUP_ASSETS].find({"user_id": uid}, {"_id": 0})
                     .sort("uploaded_at", -1).limit(6))
    recent_assets = await recent_cursor.to_list(length=6)

    recent: list[ResultListItem] = []
    for asset in recent_assets:
        result = await db[Collections.HEATMAP_RESULTS].find_one(
            {"asset_id": asset["asset_id"]}, {"_id": 0})
        recent.append(ResultListItem(
            asset_id=asset["asset_id"], project_id=asset["project_id"],
            original_filename=asset["original_filename"], status=asset["status"],
            uploaded_at=asset["uploaded_at"],
            clarity_score=(result or {}).get("clarity_score"),
            heatmap_url=(result or {}).get("heatmap_url"),
            mockup_url=asset.get("file_url"),
            width=asset.get("width", 0), height=asset.get("height", 0),
        ))

    return DashboardStats(
        total_projects=total_projects, total_analyses=total_analyses,
        avg_clarity_score=avg_clarity, projects_this_month=projects_this_month,
        clarity_trend=trend, recent_assets=recent,
    )
