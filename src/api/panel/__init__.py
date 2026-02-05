"""Panel API router aggregation."""

from fastapi import APIRouter

from src.api.panel.chat import router as chat_router
from src.api.panel.dashboard import router as dashboard_router
from src.api.panel.deals import router as deals_router
from src.api.panel.profile import router as profile_router

panel_router = APIRouter(prefix="/panel", tags=["Panel"])

panel_router.include_router(dashboard_router, prefix="/dashboard")
panel_router.include_router(deals_router)
panel_router.include_router(chat_router)
panel_router.include_router(profile_router)

__all__ = ["panel_router"]
