"""Admin API router aggregation."""

from fastapi import APIRouter

from src.api.admin.audit import router as audit_router
from src.api.admin.chats import router as chats_router
from src.api.admin.dashboard import router as dashboard_router
from src.api.admin.deals import router as deals_router
from src.api.admin.finance import router as finance_router
from src.api.admin.managers import router as managers_router
from src.api.admin.orders import router as orders_router
from src.api.admin.settings import router as settings_router

admin_router = APIRouter(prefix="/admin", tags=["Admin"])

admin_router.include_router(dashboard_router)
admin_router.include_router(chats_router)
admin_router.include_router(orders_router)
admin_router.include_router(deals_router)
admin_router.include_router(managers_router)
admin_router.include_router(finance_router)
admin_router.include_router(audit_router)
admin_router.include_router(settings_router)

__all__ = ["admin_router"]
