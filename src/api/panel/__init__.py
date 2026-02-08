"""Panel API router aggregation."""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from src.api.panel.announcements import router as announcements_router
from src.api.panel.chat import router as chat_router
from src.api.panel.dashboard import router as dashboard_router
from src.api.panel.deals import router as deals_router
from src.api.panel.leads import router as leads_router
from src.api.panel.notifications import router as notifications_router
from src.api.panel.profile import router as profile_router

panel_router = APIRouter(prefix="/panel", tags=["Panel"])


@panel_router.get("", include_in_schema=False)
async def panel_root():
    """Redirect /panel to /panel/dashboard."""
    return RedirectResponse(url="/panel/dashboard", status_code=302)


panel_router.include_router(dashboard_router, prefix="/dashboard")
panel_router.include_router(deals_router)
panel_router.include_router(leads_router)
panel_router.include_router(chat_router)
panel_router.include_router(profile_router)
panel_router.include_router(notifications_router)
panel_router.include_router(announcements_router)

__all__ = ["panel_router"]
