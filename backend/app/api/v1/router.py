"""Aggregate router for /api/v1."""

from fastapi import APIRouter

from app.api.v1 import auth, compare, health, projects, results, suggestions, uploads

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(uploads.router)
api_router.include_router(results.router)
api_router.include_router(compare.router)
api_router.include_router(suggestions.router)
