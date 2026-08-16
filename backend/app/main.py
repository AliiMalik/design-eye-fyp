"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.auth import limiter
from app.api.v1.router import api_router
from app.config import settings
from app.db.indexes import ensure_indexes
from app.db.mongo import close_mongo_connection, connect_to_mongo
from app.ml.inference import get_model_meta, load_model

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect the database and load the model once, at process start."""
    logger.info("Starting %s v%s (env=%s, dev_mode=%s)",
                settings.APP_NAME, settings.APP_VERSION,
                settings.APP_ENV, settings.DEV_MODE)

    try:
        db = await connect_to_mongo()
        await ensure_indexes(db)
    except Exception as exc:  # noqa: BLE001 - surface via /health, do not crash
        logger.error("MongoDB unavailable at startup: %s", exc)

    try:
        load_model(settings.MODEL_PATH)
        meta = get_model_meta()
        logger.info("Model ready | version=%s epoch=%s device=%s",
                    meta.get("checkpoint_model_version"), meta.get("epoch"),
                    meta.get("device"))
        if meta.get("val"):
            logger.info("Checkpoint validation metrics: %s", meta["val"])
    except Exception as exc:  # noqa: BLE001
        logger.error("Model failed to load: %s", exc)

    yield

    await close_mongo_connection()
    logger.info("Shutdown complete")


app = FastAPI(
    title="DesignEye API",
    description=(
        "Predictive visual-attention analysis for static UI mockups. "
        "Upload a mockup, receive a saliency heatmap, Clarity Score, Focus "
        "Order, and grounded design suggestions."
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,   # explicit allow-list, never "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router, prefix=API_PREFIX)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log the detail server-side, return an opaque 500 to the client."""
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc,
                 exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )


if settings.STORAGE_BACKEND == "local":
    storage_dir = Path(settings.STORAGE_LOCAL_DIR)
    storage_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/storage", StaticFiles(directory=str(storage_dir)), name="storage")


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api": API_PREFIX,
    }


@app.get("/health", include_in_schema=False)
async def health_alias():
    """Unprefixed alias so container healthchecks have a stable path."""
    from app.api.v1.health import health

    return await health()
