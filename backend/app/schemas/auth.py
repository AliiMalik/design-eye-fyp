"""Authentication request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

PASSWORD_MIN = 8
PASSWORD_MAX = 72  # bcrypt's hard limit, in bytes


def _validate_password(v: str) -> str:
    if len(v) < PASSWORD_MIN:
        raise ValueError(f"Password must be at least {PASSWORD_MIN} characters.")
    if len(v.encode("utf-8")) > PASSWORD_MAX:
        raise ValueError(f"Password must be at most {PASSWORD_MAX} bytes.")
    if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
        raise ValueError("Password must contain at least one letter and one number.")
    return v


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password(v)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ResetPasswordRequest(BaseModel):
    email: EmailStr


class ConfirmResetRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password(v)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return _validate_password(v)


class UserResponse(BaseModel):
    user_id: str
    email: EmailStr
    display_name: str | None = None
    role: str = "designer"
    bio: str | None = None
    avatar_url: str | None = None
    is_active: bool = True
    created_at: datetime


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=250)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
