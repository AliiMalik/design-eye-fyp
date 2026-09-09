"""FastAPI dependencies: authentication and tenant-scoped resource access."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.errors import forbidden, not_found, unauthorized
from app.core.security import TokenError, decode_token, token_predates_revocation
from app.db.mongo import Collections, get_database

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIOMotorDatabase:
    return get_database()


DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbDep,
) -> dict[str, Any]:
    """Resolve the bearer token to a user document.

    Missing, malformed, or expired token -> 401 (TC-11, TC-14).
    """
    if credentials is None or not credentials.credentials:
        raise unauthorized()

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise unauthorized(str(exc)) from exc

    user = await db[Collections.USERS].find_one({"user_id": payload["sub"]}, {"_id": 0})
    if user is None:
        raise unauthorized("User no longer exists")
    if not user.get("is_active", True):
        raise forbidden("Account is disabled")
    # Closes the window a password reset would otherwise leave open: without
    # this an access token issued beforehand keeps working until it expires.
    if token_predates_revocation(user, payload):
        raise unauthorized("This session has been revoked. Please log in again.")
    return user


CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


async def owned_or_403(db: AsyncIOMotorDatabase, collection: str, id_field: str,
                       id_value: str, user_id: str, label: str) -> dict[str, Any]:
    """Fetch a document by id and assert the caller owns it.

    Deliberately looks the document up WITHOUT the user filter so that another
    user's resource yields 403 rather than 404 (SDS test case TC-12).
    """
    doc = await db[collection].find_one({id_field: id_value}, {"_id": 0})
    if doc is None:
        raise not_found(label)
    if doc.get("user_id") != user_id:
        raise forbidden(f"You do not have access to this {label.lower()}")
    return doc


async def get_owned_project(db: AsyncIOMotorDatabase, project_id: str,
                            user_id: str) -> dict[str, Any]:
    return await owned_or_403(db, Collections.PROJECTS, "project_id",
                              project_id, user_id, "Project")


async def get_owned_asset(db: AsyncIOMotorDatabase, asset_id: str,
                          user_id: str) -> dict[str, Any]:
    return await owned_or_403(db, Collections.MOCKUP_ASSETS, "asset_id",
                              asset_id, user_id, "Asset")


async def get_owned_task(db: AsyncIOMotorDatabase, task_id: str,
                         user_id: str) -> dict[str, Any]:
    return await owned_or_403(db, Collections.INFERENCE_TASKS, "task_id",
                              task_id, user_id, "Task")


async def get_owned_comparison(db: AsyncIOMotorDatabase, comparison_id: str,
                               user_id: str) -> dict[str, Any]:
    return await owned_or_403(db, Collections.AB_COMPARISONS, "comparison_id",
                              comparison_id, user_id, "Comparison")
