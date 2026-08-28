"""Authentication endpoints (SDS API table + BUILD.md section 8 additions).

NOTE: this module must NOT use ``from __future__ import annotations``.
The slowapi ``@limiter.limit`` decorator replaces the route function, and
FastAPI resolves string annotations against ``call.__globals__`` -- which for a
wrapped function is slowapi's module namespace, not ours. With postponed
annotations the request models silently degrade to query parameters and every
rate-limited endpoint 422s. Keep the annotations evaluated eagerly.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, Request, UploadFile, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings
from app.core.deps import CurrentUser, DbDep
from app.core.errors import bad_request, conflict, unauthorized
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.mongo import Collections
from app.models.domain import User, utcnow
from app.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    ConfirmResetRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.schemas.common import MessageResponse
from app.services.avatars import avatar_key, build_avatar
from app.services.images import UnsupportedFileError
from app.services.storage import StorageService, get_storage

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["auth"])

RESET_TOKEN_TTL_MINUTES = 30


def _user_response(doc: dict) -> UserResponse:
    key = doc.get("avatar_key")
    return UserResponse(
        user_id=doc["user_id"], email=doc["email"],
        display_name=doc.get("display_name"), role=doc.get("role", "designer"),
        bio=doc.get("bio"), is_active=doc.get("is_active", True),
        avatar_url=get_storage().url_for(key) if key else None,
        created_at=doc["created_at"],
    )


def _discard(storage: StorageService, key: str | None, keep: str) -> None:
    """Drop a replaced avatar. Best effort -- an orphaned object is untidy, but
    failing someone's upload because the old one would not delete is worse.

    ``keep`` guards the re-upload of an identical picture: the key is the
    content hash, so the "previous" object is the one just written."""
    if not key or key == keep:
        return
    try:
        storage.delete(key)
    except Exception:  # noqa: BLE001 - never fail the request over cleanup
        logger.warning("Could not remove the previous avatar %s", key)


async def _issue_tokens(db, user: dict) -> TokenResponse:
    access = create_access_token(user["user_id"], user["email"])
    refresh, jti, expires_at = create_refresh_token(user["user_id"])
    await db[Collections.USERS].update_one(
        {"user_id": user["user_id"]}, {"$set": {"last_login_at": utcnow()}})
    return TokenResponse(
        access_token=access, refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_user_response(user),
    )


@router.post("/register", response_model=TokenResponse,
             status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.AUTH_RATE_LIMIT)
async def register(request: Request, payload: RegisterRequest, db: DbDep) -> TokenResponse:
    """Create an account (TC-01). A duplicate email is rejected (TC-02)."""
    email = payload.email.lower().strip()
    if await db[Collections.USERS].find_one({"email": email}, {"_id": 1}):
        raise conflict("Email already in use.")

    user = User(
        email=email,
        display_name=payload.display_name or email.split("@")[0],
        password_hash=hash_password(payload.password),
    )
    user.tenant_prefix = user.user_id
    doc = user.to_mongo()

    try:
        await db[Collections.USERS].insert_one(dict(doc))
    except Exception as exc:  # unique index catches a concurrent duplicate
        if "duplicate" in str(exc).lower() or "E11000" in str(exc):
            raise conflict("Email already in use.") from exc
        raise

    logger.info("Registered user %s", user.user_id)
    return await _issue_tokens(db, doc)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.AUTH_RATE_LIMIT)
async def login(request: Request, payload: LoginRequest, db: DbDep) -> TokenResponse:
    """Exchange credentials for an access + refresh token pair."""
    email = payload.email.lower().strip()
    user = await db[Collections.USERS].find_one({"email": email}, {"_id": 0})

    # Same generic message either way, so the endpoint cannot enumerate accounts.
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise unauthorized("Invalid email or password.")
    if not user.get("is_active", True):
        raise unauthorized("This account is disabled.")

    return await _issue_tokens(db, user)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_token(payload: RefreshRequest, db: DbDep) -> AccessTokenResponse:
    """Mint a new access token from a refresh token that is not denylisted."""
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise unauthorized(str(exc)) from exc

    if await db[Collections.REFRESH_DENYLIST].find_one({"jti": claims["jti"]}, {"_id": 1}):
        raise unauthorized("This session has been revoked. Please log in again.")

    user = await db[Collections.USERS].find_one({"user_id": claims["sub"]}, {"_id": 0})
    if user is None or not user.get("is_active", True):
        raise unauthorized("Account is unavailable.")

    return AccessTokenResponse(
        access_token=create_access_token(user["user_id"], user["email"]),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(payload: LogoutRequest, user: CurrentUser, db: DbDep) -> MessageResponse:
    """Revoke a refresh token by denylisting its jti until it would expire."""
    if payload.refresh_token:
        try:
            claims = decode_token(payload.refresh_token, expected_type="refresh")
            await db[Collections.REFRESH_DENYLIST].update_one(
                {"jti": claims["jti"]},
                {"$set": {
                    "jti": claims["jti"],
                    "user_id": claims["sub"],
                    "expires_at": datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
                }},
                upsert=True,
            )
        except TokenError:
            pass  # an unusable token needs no revoking
    return MessageResponse(message="Logged out")


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit(settings.AUTH_RATE_LIMIT)
async def request_password_reset(request: Request, payload: ResetPasswordRequest,
                                 db: DbDep) -> MessageResponse:
    """Start a password reset.

    There is no mail service in this build, so the token is stored and logged
    server-side; in DEV_MODE it is also returned so the flow is demonstrable.
    See docs/DEVIATIONS.md.
    """
    email = payload.email.lower().strip()
    user = await db[Collections.USERS].find_one({"email": email}, {"_id": 0, "user_id": 1})

    if user is not None:
        token = secrets.token_urlsafe(32)
        await db[Collections.USERS].update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "reset_token": token,
                "reset_token_expires": datetime.now(timezone.utc)
                + timedelta(minutes=RESET_TOKEN_TTL_MINUTES),
            }},
        )
        logger.info("Password reset token issued for %s: %s", email, token)
        if settings.DEV_MODE:
            return MessageResponse(message=f"Reset link sent. DEV_MODE token: {token}")

    # Always the same reply, so this cannot be used to enumerate accounts.
    return MessageResponse(message="Reset link sent")


@router.post("/reset-password/confirm", response_model=MessageResponse)
async def confirm_password_reset(payload: ConfirmResetRequest, db: DbDep) -> MessageResponse:
    user = await db[Collections.USERS].find_one({"reset_token": payload.token}, {"_id": 0})
    if user is None:
        raise bad_request("This reset link is invalid or has already been used.")

    expires = user.get("reset_token_expires")
    if expires is None or expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise bad_request("This reset link has expired. Please request a new one.")

    await db[Collections.USERS].update_one(
        {"user_id": user["user_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "updated_at": utcnow()},
         "$unset": {"reset_token": "", "reset_token_expires": ""}},
    )
    return MessageResponse(message="Password updated. You can now log in.")


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser) -> UserResponse:
    return _user_response(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(payload: UpdateProfileRequest, user: CurrentUser,
                    db: DbDep) -> UserResponse:
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if updates:
        updates["updated_at"] = utcnow()
        await db[Collections.USERS].update_one({"user_id": user["user_id"]},
                                               {"$set": updates})
    fresh = await db[Collections.USERS].find_one({"user_id": user["user_id"]}, {"_id": 0})
    return _user_response(fresh)


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(user: CurrentUser, db: DbDep,
                        file: UploadFile = File(...)) -> UserResponse:
    """Replace the signed-in user's profile picture."""
    try:
        data = build_avatar(await file.read())
    except UnsupportedFileError as exc:
        raise bad_request(str(exc)) from exc

    storage = get_storage()
    key = avatar_key(user["user_id"], data)
    storage.save_bytes(key, data, "image/png")
    await db[Collections.USERS].update_one(
        {"user_id": user["user_id"]},
        {"$set": {"avatar_key": key, "updated_at": utcnow()}},
    )
    _discard(storage, user.get("avatar_key"), key)

    fresh = await db[Collections.USERS].find_one({"user_id": user["user_id"]}, {"_id": 0})
    return _user_response(fresh)


@router.delete("/me/avatar", response_model=UserResponse)
async def remove_avatar(user: CurrentUser, db: DbDep) -> UserResponse:
    await db[Collections.USERS].update_one(
        {"user_id": user["user_id"]},
        {"$unset": {"avatar_key": ""}, "$set": {"updated_at": utcnow()}},
    )
    _discard(get_storage(), user.get("avatar_key"), "")

    fresh = await db[Collections.USERS].find_one({"user_id": user["user_id"]}, {"_id": 0})
    return _user_response(fresh)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(payload: ChangePasswordRequest, user: CurrentUser,
                          db: DbDep) -> MessageResponse:
    if not verify_password(payload.current_password, user["password_hash"]):
        raise bad_request("Your current password is incorrect.")
    await db[Collections.USERS].update_one(
        {"user_id": user["user_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password),
                  "updated_at": utcnow()}},
    )
    return MessageResponse(message="Password updated")
