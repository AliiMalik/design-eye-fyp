"""Password hashing and JWT issue/verify (BUILD.md section 9).

Entirely Python: passlib[bcrypt] + PyJWT. No Firebase, no Auth0, no Clerk.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

from app.config import settings

logger = logging.getLogger(__name__)

# passlib probes bcrypt.__about__, removed in bcrypt>=4.1; the warning is noise.
logging.getLogger("passlib.handlers.bcrypt").setLevel(logging.ERROR)

pwd_context = CryptContext(
    schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.BCRYPT_ROUNDS,
)

BCRYPT_MAX_BYTES = 72
TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or revoked."""


def hash_password(password: str) -> str:
    """Hash a plaintext password. The plaintext is never stored or logged."""
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError("Password exceeds the 72-byte bcrypt limit.")
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        if len(plain.encode("utf-8")) > BCRYPT_MAX_BYTES:
            return False
        return pwd_context.verify(plain, hashed)
    except Exception:  # noqa: BLE001 - a malformed hash must not 500
        return False


def _create_token(subject: str, token_type: TokenType, expires: timedelta,
                  extra: dict[str, Any] | None = None) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + expires
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expires_at


def create_access_token(user_id: str, email: str | None = None) -> str:
    token, _, _ = _create_token(
        user_id, "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        {"email": email} if email else None,
    )
    return token


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    """Return (token, jti, expires_at); the jti is what logout denylists."""
    return _create_token(
        user_id, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Decode and validate a JWT. Raises TokenError on any failure.

    An expired token raises TokenError, which the API layer turns into 401
    (SDS test case TC-14).
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc

    if expected_type and payload.get("type") != expected_type:
        raise TokenError(f"Expected a {expected_type} token")
    if not payload.get("sub"):
        raise TokenError("Token is missing a subject")
    return payload
