"""Admin managers API endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_owner
from src.db import get_db
from src.models import (
    AuditAction,
    AuditLog,
    DealStatus,
    DetectedDeal,
    LedgerEntry,
    NegotiationMessage,
    User,
    UserRole,
)
from src.models.user import generate_invite_token
from src.schemas.user import (
    ManagerCreate,
    ManagerResponse,
    ManagerStatsResponse,
    ManagerUpdate,
)
from src.utils.audit import get_client_ip, log_action
from src.utils.password import hash_password

router = APIRouter(prefix="/managers")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def managers_page(
    request: Request,
    current_user: User = Depends(require_owner),
):
    """Render managers page."""
    return templates.TemplateResponse(
        "admin/managers.html",
        {"request": request, "user": current_user},
    )


@router.get("/list")
async def list_managers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
    active_only: bool = Query(False),
):
    """List all managers with stats."""
    query = select(User).where(User.role == UserRole.MANAGER)

    if active_only:
        query = query.where(User.is_active == True)

    query = query.order_by(User.display_name)

    result = await db.execute(query)
    managers = result.scalars().all()

    # Build response with stats
    items = []
    for manager in managers:
        # Get deal counts
        deal_counts = await db.execute(
            select(
                func.count()
                .filter(
                    DetectedDeal.status.in_(
                        [DealStatus.IN_PROGRESS, DealStatus.WARM, DealStatus.HANDED_TO_MANAGER]
                    )
                )
                .label("active"),
                func.count().filter(DetectedDeal.status == DealStatus.WON).label("won"),
                func.count().filter(DetectedDeal.status == DealStatus.LOST).label("lost"),
            )
            .select_from(DetectedDeal)
            .where(DetectedDeal.manager_id == manager.id)
        )
        counts = deal_counts.one()

        # Calculate conversion rate
        total_closed = counts.won + counts.lost
        conversion = (counts.won / total_closed * 100) if total_closed > 0 else 0

        # Get average deal value
        avg_value = await db.scalar(
            select(func.avg(LedgerEntry.profit))
            .select_from(LedgerEntry)
            .join(DetectedDeal)
            .where(DetectedDeal.manager_id == manager.id)
        )

        items.append(
            ManagerResponse(
                id=manager.id,
                username=manager.username,
                display_name=manager.display_name,
                is_active=manager.is_active,
                created_at=manager.created_at,
                last_active_at=manager.last_active_at,
                invite_token=manager.invite_token,
                active_deals_count=counts.active,
                won_deals_count=counts.won,
                lost_deals_count=counts.lost,
                conversion_rate=round(conversion, 1),
                avg_deal_value=avg_value or Decimal("0.00"),
            )
        )

    return {"items": items}


@router.get("/{manager_id}/data", response_model=ManagerResponse)
async def get_manager(
    manager_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Get manager details."""
    manager = await db.get(User, manager_id)

    if not manager or manager.role != UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manager not found",
        )

    # Get stats
    deal_counts = await db.execute(
        select(
            func.count()
            .filter(
                DetectedDeal.status.in_(
                    [DealStatus.IN_PROGRESS, DealStatus.WARM, DealStatus.HANDED_TO_MANAGER]
                )
            )
            .label("active"),
            func.count().filter(DetectedDeal.status == DealStatus.WON).label("won"),
            func.count().filter(DetectedDeal.status == DealStatus.LOST).label("lost"),
        )
        .select_from(DetectedDeal)
        .where(DetectedDeal.manager_id == manager.id)
    )
    counts = deal_counts.one()

    total_closed = counts.won + counts.lost
    conversion = (counts.won / total_closed * 100) if total_closed > 0 else 0

    avg_value = await db.scalar(
        select(func.avg(LedgerEntry.profit))
        .select_from(LedgerEntry)
        .join(DetectedDeal)
        .where(DetectedDeal.manager_id == manager.id)
    )

    return ManagerResponse(
        id=manager.id,
        username=manager.username,
        display_name=manager.display_name,
        is_active=manager.is_active,
        created_at=manager.created_at,
        last_active_at=manager.last_active_at,
        invite_token=manager.invite_token,
        active_deals_count=counts.active,
        won_deals_count=counts.won,
        lost_deals_count=counts.lost,
        conversion_rate=round(conversion, 1),
        avg_deal_value=avg_value or Decimal("0.00"),
    )


@router.get("/{manager_id}/stats", response_model=ManagerStatsResponse)
async def get_manager_stats(
    manager_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Get detailed manager statistics."""
    manager = await db.get(User, manager_id)

    if not manager or manager.role != UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manager not found",
        )

    # Deal counts
    deal_counts = await db.execute(
        select(
            func.count().label("total"),
            func.count()
            .filter(
                DetectedDeal.status.in_(
                    [DealStatus.IN_PROGRESS, DealStatus.WARM, DealStatus.HANDED_TO_MANAGER]
                )
            )
            .label("active"),
            func.count().filter(DetectedDeal.status == DealStatus.WON).label("won"),
            func.count().filter(DetectedDeal.status == DealStatus.LOST).label("lost"),
        )
        .select_from(DetectedDeal)
        .where(DetectedDeal.manager_id == manager.id)
    )
    counts = deal_counts.one()

    total_closed = counts.won + counts.lost
    conversion = (counts.won / total_closed * 100) if total_closed > 0 else 0

    # Profit stats
    profit_stats = await db.execute(
        select(
            func.avg(LedgerEntry.profit).label("avg"),
            func.sum(LedgerEntry.profit).label("total"),
        )
        .select_from(LedgerEntry)
        .join(DetectedDeal)
        .where(DetectedDeal.manager_id == manager.id)
    )
    profits = profit_stats.one()

    # Messages count
    messages_count = await db.scalar(
        select(func.count())
        .select_from(NegotiationMessage)
        .where(NegotiationMessage.sent_by_user_id == manager.id)
    )

    return ManagerStatsResponse(
        id=manager.id,
        display_name=manager.display_name,
        total_deals=counts.total,
        active_deals=counts.active,
        won_deals=counts.won,
        lost_deals=counts.lost,
        conversion_rate=round(conversion, 1),
        avg_close_time_hours=None,  # TODO: Calculate from deal timestamps
        avg_profit=profits.avg or Decimal("0.00"),
        total_profit=profits.total or Decimal("0.00"),
        messages_sent=messages_count or 0,
        last_active_at=manager.last_active_at,
    )


@router.get("/{manager_id}/audit")
async def get_manager_audit(
    manager_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    """Get manager's audit log."""
    manager = await db.get(User, manager_id)

    if not manager or manager.role != UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manager not found",
        )

    # Get audit logs
    query = (
        select(AuditLog)
        .where(AuditLog.user_id == manager_id)
        .order_by(AuditLog.created_at.desc())
    )

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    )

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "items": [
            {
                "id": log.id,
                "action": log.action.value,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "metadata": log.metadata,
                "ip_address": log.ip_address,
                "created_at": log.created_at,
            }
            for log in logs
        ],
        "total": total or 0,
        "page": page,
        "per_page": per_page,
    }


@router.post("")
async def create_manager(
    request: Request,
    data: ManagerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Create a new manager account."""
    # Check if username exists
    existing = await db.execute(
        select(User).where(User.username == data.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    manager = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=UserRole.MANAGER,
        display_name=data.display_name,
        is_active=True,
        invite_token=generate_invite_token(),
    )
    db.add(manager)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.CREATE_MANAGER,
        target_type="user",
        action_metadata={"username": data.username, "display_name": data.display_name},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    await db.refresh(manager)

    return {"success": True, "id": manager.id}


@router.put("/{manager_id}")
async def update_manager(
    request: Request,
    manager_id: int,
    data: ManagerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Update manager account."""
    manager = await db.get(User, manager_id)

    if not manager or manager.role != UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manager not found",
        )

    if data.display_name is not None:
        manager.display_name = data.display_name

    if data.is_active is not None:
        manager.is_active = data.is_active

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.UPDATE_MANAGER,
        target_type="user",
        target_id=manager_id,
        action_metadata=data.model_dump(exclude_none=True),
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True}


@router.delete("/{manager_id}")
async def deactivate_manager(
    request: Request,
    manager_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Deactivate a manager account."""
    manager = await db.get(User, manager_id)

    if not manager or manager.role != UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manager not found",
        )

    manager.is_active = False

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.DELETE_MANAGER,
        target_type="user",
        target_id=manager_id,
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True}


@router.post("/{manager_id}/reset-password")
async def reset_manager_password(
    request: Request,
    manager_id: int,
    new_password: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Reset manager's password."""
    manager = await db.get(User, manager_id)

    if not manager or manager.role != UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manager not found",
        )

    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters",
        )

    manager.password_hash = hash_password(new_password)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.UPDATE_MANAGER,
        target_type="user",
        target_id=manager_id,
        action_metadata={"action": "password_reset"},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True}


@router.post("/{manager_id}/regenerate-token")
async def regenerate_manager_token(
    request: Request,
    manager_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """
    Regenerate manager's invite token.

    Use this to invalidate old links (e.g., when firing a manager
    but keeping their account for records).
    """
    manager = await db.get(User, manager_id)

    if not manager or manager.role != UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manager not found",
        )

    old_token = manager.invite_token
    manager.invite_token = generate_invite_token()

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.UPDATE_MANAGER,
        target_type="user",
        target_id=manager_id,
        action_metadata={"action": "token_regenerated", "old_token_prefix": old_token[:8] if old_token else None},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True, "invite_token": manager.invite_token}


# IMPORTANT: This route MUST be after all other /{manager_id}/... routes
# to avoid "data", "stats", "audit", etc. being interpreted as manager_id
@router.get("/{manager_id}", response_class=HTMLResponse, include_in_schema=False)
async def manager_detail_page(
    request: Request,
    manager_id: int,
    current_user: User = Depends(require_owner),
):
    """Render manager detail page."""
    return templates.TemplateResponse(
        "admin/manager_detail.html",
        {"request": request, "user": current_user, "manager_id": manager_id},
    )
