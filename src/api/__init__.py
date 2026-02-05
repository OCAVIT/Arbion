"""API router aggregation."""

from fastapi import APIRouter

from src.api.admin import admin_router
from src.api.auth import router as auth_router
from src.api.health import router as health_router
from src.api.panel import panel_router

# Main API router (for /api/* endpoints)
api_router = APIRouter(prefix="/api")

# Include API sub-routers
api_router.include_router(health_router)
api_router.include_router(auth_router)

# Web interface routers (mounted directly, not under /api)
__all__ = ["api_router", "admin_router", "panel_router"]
