"""Admin API router aggregation."""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from src.api.admin.analytics import router as analytics_router
from src.api.admin.audit import router as audit_router
from src.api.admin.chats import router as chats_router
from src.api.admin.dashboard import router as dashboard_router
from src.api.admin.deals import router as deals_router
from src.api.admin.finance import router as finance_router
from src.api.admin.managers import router as managers_router
from src.api.admin.orders import router as orders_router
from src.api.admin.settings import router as settings_router

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@admin_router.get("", include_in_schema=False)
async def admin_root():
    """Redirect /admin to /admin/dashboard."""
    return RedirectResponse(url="/admin/dashboard", status_code=302)


admin_router.include_router(dashboard_router, prefix="/dashboard")
admin_router.include_router(chats_router)
admin_router.include_router(orders_router)
admin_router.include_router(deals_router)
admin_router.include_router(managers_router)
admin_router.include_router(finance_router)
admin_router.include_router(analytics_router)
admin_router.include_router(audit_router)
admin_router.include_router(settings_router)

__all__ = ["admin_router"]
