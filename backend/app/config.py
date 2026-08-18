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
    # A real multi-screen Figma export runs well past 10MB, and unlike an image
    # the PDF itself is never stored -- only the rasterised pages are.
    MAX_PDF_UPLOAD_MB: int = 20
    MAX_IMAGE_LONG_SIDE: int = 8000
    # A full-page export is legitimately enormous down one axis -- seven phone
    # screens at 900px wide is 13650px tall. Capping the LONG side at 8000
    # rejected exactly the uploads viewport segmentation exists to handle, and it
    # was a poor proxy for cost anyway: 900x13650 is 12M pixels, while the
    # permitted 8000x8000 is 64M. The short side and the total pixel count
    # (Image.MAX_IMAGE_PIXELS) are the limits that actually bound the work.
    MAX_SCROLL_LONG_SIDE: int = 30000

    # --- llm ---
    LLM_PROVIDER: str = "mock"
    LLM_MODEL: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LLM_RATE_LIMIT_PER_DAY: int = 50
    LLM_TIMEOUT_SECONDS: int = 90

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

    # The byte ceilings live in services/images.size_limit_mb(), which picks one
    # per format. Two properties here would just be a second place to disagree.


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
