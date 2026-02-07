"""Manager panel dashboard API endpoints."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_manager
from src.db import get_db
from src.models import DealStatus, DetectedDeal, LedgerEntry, SystemSetting, User, UserRole
from src.schemas.dashboard import ManagerPanelStatsResponse

router = APIRouter()
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def panel_dashboard_page(
    request: Request,
    current_user: User = Depends(require_manager),
):
    """Render manager panel dashboard."""
    return templates.TemplateResponse(
        "panel/dashboard.html",
        {"request": request, "user": current_user},
    )


@router.get("/stats", response_model=ManagerPanelStatsResponse)
async def get_panel_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Get manager's personal stats."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Active deals for this manager
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

    # Warm leads in pool (unassigned)
    # Check if assignment mode is free_pool
    mode_setting = await db.get(SystemSetting, "assignment_mode")
    assignment_mode = mode_setting.get_value() if mode_setting else "free_pool"

    warm_in_pool = 0
    if assignment_mode == "free_pool":
        warm_in_pool = await db.scalar(
            select(func.count())
            .select_from(DetectedDeal)
            .where(
                and_(
                    DetectedDeal.manager_id.is_(None),
                    DetectedDeal.status.in_([DealStatus.WARM, DealStatus.COLD]),
                )
            )
        )

    # Total earned from commissions
    total_earned = await db.scalar(
        select(func.sum(LedgerEntry.manager_commission))
        .select_from(LedgerEntry)
        .join(DetectedDeal)
        .where(DetectedDeal.manager_id == current_user.id)
    )

    return ManagerPanelStatsResponse(
        active_deals=active_deals or 0,
        closed_this_month=total_closed,
        conversion_rate=round(conversion, 1),
        warm_leads_in_pool=warm_in_pool or 0,
        total_earned=total_earned or Decimal("0.00"),
    )


@router.get("/pool")
async def get_warm_pool(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Get warm leads in the free pool (unassigned)."""
    from src.schemas.deal import ManagerDealResponse

    # Check assignment mode
    mode_setting = await db.get(SystemSetting, "assignment_mode")
    assignment_mode = mode_setting.get_value() if mode_setting else "free_pool"

    if assignment_mode != "free_pool":
        return {"items": [], "message": "Auto-assignment mode is active"}

    # Get unassigned warm and cold deals (cold = copilot mode new leads)
    result = await db.execute(
        select(DetectedDeal)
        .where(
            and_(
                DetectedDeal.manager_id.is_(None),
                DetectedDeal.status.in_([DealStatus.WARM, DealStatus.COLD]),
            )
        )
        .order_by(DetectedDeal.created_at.desc())
        .limit(20)
    )
    deals = result.scalars().all()

    # Check if manager can take more deals
    max_setting = await db.get(SystemSetting, "max_deals_per_manager")
    max_deals = max_setting.get_value() if max_setting else 15

    active_count = await db.scalar(
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

    can_take = active_count < max_deals
    blocked_reason = None if can_take else "Достигнут лимит активных сделок"

    items = []
    for deal in deals:
        items.append(
            ManagerDealResponse.from_deal(
                deal,
                negotiation=deal.negotiation,
                can_take=can_take,
                take_blocked_reason=blocked_reason,
            )
        )

    return {"items": items}
