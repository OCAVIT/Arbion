"""Admin settings API endpoints."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_owner
from src.db import get_db
from src.models import AuditAction, SystemSetting, User
from src.schemas.settings import SettingsResponse, SettingsUpdate
from src.utils.audit import get_client_ip, log_action

router = APIRouter(prefix="/settings")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def settings_page(
    request: Request,
    current_user: User = Depends(require_owner),
):
    """Render settings page."""
    return templates.TemplateResponse(
        "admin/settings.html",
        {"request": request, "user": current_user},
    )


@router.get("/data", response_model=SettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Get all system settings."""
    result = await db.execute(select(SystemSetting))
    settings_list = result.scalars().all()

    settings_dict = {s.key: s.get_value() for s in settings_list}

    return SettingsResponse(
        target_chat_count=settings_dict.get("target_chat_count", 100),
        assignment_mode=settings_dict.get("assignment_mode", "free_pool"),
        max_deals_per_manager=settings_dict.get("max_deals_per_manager", 15),
        min_margin_threshold=settings_dict.get("min_margin_threshold", 5.0),
        parser_interval_minutes=settings_dict.get("parser_interval_minutes", 5),
        matcher_interval_minutes=settings_dict.get("matcher_interval_minutes", 10),
        negotiator_interval_minutes=settings_dict.get("negotiator_interval_minutes", 15),
        seed_queries=settings_dict.get("seed_queries", []),
        messaging_mode=settings_dict.get("messaging_mode", "personal"),
    )


@router.put("/data")
async def update_settings(
    request: Request,
    data: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Update system settings."""
    updated_keys = []

    for key, value in data.model_dump(exclude_none=True).items():
        setting = await db.get(SystemSetting, key)
        if setting:
            setting.set_value(value)
        else:
            setting = SystemSetting(key=key, value={"v": value})
            db.add(setting)
        updated_keys.append(key)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.UPDATE_SETTINGS,
        action_metadata={"updated_keys": updated_keys},
        ip_address=get_client_ip(request),
    )

    await db.commit()

    return {"success": True, "updated_keys": updated_keys}
