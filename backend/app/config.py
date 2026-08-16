"""Application settings, loaded from environment / .env (Pydantic v2)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    APP_ENV: str = "development"
    APP_NAME: str = "DesignEye"
    APP_VERSION: str = "1.0.0"
    DEV_MODE: bool = True
    LOG_LEVEL: str = "INFO"

    # --- cors ---
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- database ---
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "designeye"
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- auth ---
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BCRYPT_ROUNDS: int = 12

    # --- storage ---
    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_DIR: str = "./storage"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # --- model ---
    MODEL_PATH: str = "app/ml/weights/stage3_ui_best_val.pth"
    MODEL_VERSION: str = "stage3-ui-v1"
    MAX_UPLOAD_MB: int = 10
    MAX_IMAGE_LONG_SIDE: int = 8000

    # --- llm ---
    LLM_PROVIDER: str = "mock"
    LLM_MODEL: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LLM_RATE_LIMIT_PER_DAY: int = 50

    # --- rate limiting ---
    AUTH_RATE_LIMIT: str = "10/minute"

    @field_validator("STORAGE_BACKEND")
    @classmethod
    def _valid_storage(cls, v: str) -> str:
        allowed = {"local", "cloudinary"}
        if v not in allowed:
            raise ValueError(f"STORAGE_BACKEND must be one of {allowed}")
        return v

    @field_validator("LLM_PROVIDER")
    @classmethod
    def _valid_llm(cls, v: str) -> str:
        allowed = {"anthropic", "openai", "gemini", "mock", "none"}
        if v not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {allowed}")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS allow-list; never '*' (BUILD.md section 9)."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
