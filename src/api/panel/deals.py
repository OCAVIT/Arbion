"""Manager panel deals API endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_manager
from src.db import get_db
from src.models import (
    AuditAction,
    DealStatus,
    DetectedDeal,
    Negotiation,
    NegotiationMessage,
    Order,
    SystemSetting,
    User,
)
from src.schemas.deal import ManagerDealListResponse, ManagerDealResponse
from src.services.commission import calculate_commission_rate
from src.utils.audit import get_client_ip, log_action

router = APIRouter(prefix="/deals")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def deals_page(
    request: Request,
    current_user: User = Depends(require_manager),
):
    """Render manager deals page."""
    return templates.TemplateResponse(
        "panel/deals.html",
        {"request": request, "user": current_user},
    )


@router.get("/list", response_model=ManagerDealListResponse)
async def list_my_deals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
    include_pool: bool = Query(True, description="Include unassigned warm deals"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """
    List deals for the current manager.

    Returns:
    - Deals assigned to this manager
    - Unassigned warm deals (if free_pool mode and include_pool=True)

    SECURITY: Only returns ManagerDealResponse (no buy_price, margin, profit)
    """
    # Build query conditions
    conditions = [DetectedDeal.manager_id == current_user.id]

    # Check assignment mode for pool access
    if include_pool:
        mode_setting = await db.get(SystemSetting, "assignment_mode")
        assignment_mode = mode_setting.get_value() if mode_setting else "free_pool"

        if assignment_mode == "free_pool":
            conditions = [
                or_(
                    DetectedDeal.manager_id == current_user.id,
                    and_(
                        DetectedDeal.manager_id.is_(None),
                        DetectedDeal.status == DealStatus.WARM,
                    ),
                )
            ]

    query = (
        select(DetectedDeal)
        .options(
            selectinload(DetectedDeal.negotiation),
            selectinload(DetectedDeal.sell_order),
            selectinload(DetectedDeal.buy_order),
        )
        .where(*conditions)
    )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Apply sorting and pagination
    query = query.order_by(DetectedDeal.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
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

    # Check messaging mode — in business_account mode, hide all contacts from manager
    messaging_mode_setting = await db.get(SystemSetting, "messaging_mode")
    messaging_mode = messaging_mode_setting.get_value() if messaging_mode_setting else "personal"

    # Build response with masked data
    items = []
    for deal in deals:
        # Count messages
        msg_count = 0
        if deal.negotiation:
            msg_count = await db.scalar(
                select(func.count())
                .select_from(NegotiationMessage)
                .where(NegotiationMessage.negotiation_id == deal.negotiation.id)
            )

        # Determine if this deal can be taken
        deal_can_take = can_take and deal.manager_id is None
        deal_blocked_reason = blocked_reason if not deal_can_take and deal.manager_id is None else None

        # Never expose seller/buyer contacts to manager
        items.append(
            ManagerDealResponse.from_deal(
                deal,
                negotiation=deal.negotiation,
                messages_count=msg_count or 0,
                can_take=deal_can_take,
                take_blocked_reason=deal_blocked_reason,
                seller_contact=None,
            )
        )

    return ManagerDealListResponse(
        items=items,
        total=total or 0,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page if total else 0,
    )


@router.post("/{deal_id}/take")
async def take_deal(
    request: Request,
    deal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Take an unassigned deal from the pool.

    Validates:
    - Deal exists and is unassigned
    - Deal is in WARM status
    - Manager hasn't reached max_deals_per_manager
    """
    deal = await db.get(DetectedDeal, deal_id)

    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сделка не найдена",
        )

    if deal.manager_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сделка уже назначена другому менеджеру",
        )

    if deal.status != DealStatus.WARM:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сделка недоступна для взятия",
        )

    # Check manager's active deal count
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

    if active_count >= max_deals:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Достигнут лимит активных сделок ({max_deals}). Закройте текущие сделки.",
        )

    # Assign deal to manager
    deal.manager_id = current_user.id
    deal.assigned_at = datetime.now(timezone.utc)
    deal.status = DealStatus.HANDED_TO_MANAGER
    deal.manager_commission_rate = calculate_commission_rate(deal, current_user)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.TAKE_DEAL,
        target_type="deal",
        target_id=deal_id,
        ip_address=get_client_ip(request),
    )

    await db.commit()

    return {"success": True, "message": "Сделка взята в работу"}
