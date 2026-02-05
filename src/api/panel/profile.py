"""Manager panel profile API endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_manager
from src.db import get_db
from src.models import DealStatus, DetectedDeal, User
from src.schemas.user import PasswordChange, ProfileResponse
from src.utils.password import hash_password, verify_password

router = APIRouter(prefix="/profile")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def profile_page(
    request: Request,
    current_user: User = Depends(require_manager),
):
    """Render profile page."""
    return templates.TemplateResponse(
        "panel/profile.html",
        {"request": request, "user": current_user},
    )


@router.get("/data", response_model=ProfileResponse)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Get current user's profile with stats."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Active deals count
    active_deals = await db.scalar(
        select(func.count())
        .select_from(DetectedDeal)
        .where(
            and_(
                DetectedDeal.manager_id == current_user.id,
                DetectedDeal.status.in_(
                    [DealStatus.IN_PROGRESS, DealStatus.WARM, DealStatus.HANDED_TO_MANAGER]
                ),
            )
        )
    )

    # Closed deals this month
    closed_query = select(
        func.count().filter(DetectedDeal.status == DealStatus.WON).label("won"),
        func.count().filter(DetectedDeal.status == DealStatus.LOST).label("lost"),
    ).select_from(DetectedDeal).where(
        and_(
            DetectedDeal.manager_id == current_user.id,
            DetectedDeal.updated_at >= month_start,
            DetectedDeal.status.in_([DealStatus.WON, DealStatus.LOST]),
        )
    )
    closed_result = await db.execute(closed_query)
    closed = closed_result.one()

    total_closed = closed.won + closed.lost
    conversion = (closed.won / total_closed * 100) if total_closed > 0 else 0

    return ProfileResponse(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        role=current_user.role.value,
        created_at=current_user.created_at,
        last_active_at=current_user.last_active_at,
        active_deals_count=active_deals or 0,
        closed_deals_month=total_closed,
        conversion_rate=round(conversion, 1),
    )


@router.put("/password")
async def change_password(
    data: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Change current user's password."""
    # Verify current password
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный текущий пароль",
        )

    # Update password
    current_user.password_hash = hash_password(data.new_password)
    await db.commit()

    return {"success": True, "message": "Пароль успешно изменён"}
