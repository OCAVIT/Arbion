"""API router aggregation."""

from fastapi import APIRouter

from src.api.admin import admin_router
from src.api.auth import router as auth_router
from src.api.health import router as health_router
from src.api.panel import panel_router

# Main API router
api_router = APIRouter(prefix="/api")

# Include sub-routers
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(panel_router)

__all__ = ["api_router"]
