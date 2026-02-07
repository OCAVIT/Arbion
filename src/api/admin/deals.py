"""Admin deals API endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_owner
from src.db import get_db
from src.models import (
    AuditAction,
    DealStatus,
    DetectedDeal,
    LedgerEntry,
    MessageRole,
    MessageTarget,
    Negotiation,
    NegotiationMessage,
    Order,
    OutboxMessage,
    User,
    UserRole,
)
from src.schemas.deal import (
    DealAssignRequest,
    DealCloseRequest,
    DealListResponse,
    DealUpdateRequest,
    MessageResponse,
    OwnerDealResponse,
    SendMessageRequest,
)
from src.services.commission import calculate_commission_rate
from src.utils.audit import get_client_ip, log_action

router = APIRouter(prefix="/deals")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def deals_page(
    request: Request,
    current_user: User = Depends(require_owner),
):
    """Render deals page."""
    return templates.TemplateResponse(
        "admin/deals.html",
        {"request": request, "user": current_user},
    )


@router.get("/list", response_model=DealListResponse)
async def list_deals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
    status_filter: Optional[str] = Query(None, alias="status"),
    product: Optional[str] = Query(None),
    manager_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List all deals with filters (full data for owner)."""
    query = select(DetectedDeal).options(
        selectinload(DetectedDeal.manager),
        selectinload(DetectedDeal.negotiation),
        selectinload(DetectedDeal.sell_order),
    )

    # Apply filters
    if status_filter:
        query = query.where(DetectedDeal.status == status_filter)

    if product:
        query = query.where(DetectedDeal.product.ilike(f"%{product}%"))

    if manager_id is not None:
        query = query.where(DetectedDeal.manager_id == manager_id)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Apply sorting and pagination
    query = query.order_by(DetectedDeal.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    deals = result.scalars().all()

    # Build response with full data
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

        resp = OwnerDealResponse(
            id=deal.id,
            product=deal.product,
            region=deal.region,
            buy_price=deal.buy_price,
            sell_price=deal.sell_price,
            margin=deal.margin,
            profit=deal.profit,
            status=deal.status,
            created_at=deal.created_at,
            updated_at=deal.updated_at,
            manager_id=deal.manager_id,
            manager_name=deal.manager.display_name if deal.manager else None,
            assigned_at=deal.assigned_at,
            buyer_chat_id=deal.buyer_chat_id,
            buyer_sender_id=deal.buyer_sender_id,
            seller_contact=deal.sell_order.contact_info if deal.sell_order else None,
            ai_insight=deal.ai_insight,
            ai_resolution=deal.ai_resolution,
            notes=deal.notes,
            target_sell_price=deal.target_sell_price,
            seller_condition=deal.seller_condition,
            seller_city=deal.seller_city,
            seller_specs=deal.seller_specs,
            seller_phone=deal.seller_phone,
            buyer_phone=deal.buyer_phone,
            negotiation_id=deal.negotiation.id if deal.negotiation else None,
            negotiation_stage=deal.negotiation.stage.value if deal.negotiation else None,
            messages_count=msg_count or 0,
        )
        items.append(resp)

    return DealListResponse(
        items=items,
        total=total or 0,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page if total else 0,
    )


@router.get("/{deal_id}/data", response_model=OwnerDealResponse)
async def get_deal(
    deal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Get full deal details."""
    result = await db.execute(
        select(DetectedDeal)
        .options(
            selectinload(DetectedDeal.manager),
            selectinload(DetectedDeal.negotiation),
            selectinload(DetectedDeal.sell_order),
        )
        .where(DetectedDeal.id == deal_id)
    )
    deal = result.scalar_one_or_none()

    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )

    # Count messages
    msg_count = 0
    if deal.negotiation:
        msg_count = await db.scalar(
            select(func.count())
            .select_from(NegotiationMessage)
            .where(NegotiationMessage.negotiation_id == deal.negotiation.id)
        )

    return OwnerDealResponse(
        id=deal.id,
        product=deal.product,
        region=deal.region,
        buy_price=deal.buy_price,
        sell_price=deal.sell_price,
        margin=deal.margin,
        profit=deal.profit,
        status=deal.status,
        created_at=deal.created_at,
        updated_at=deal.updated_at,
        manager_id=deal.manager_id,
        manager_name=deal.manager.display_name if deal.manager else None,
        assigned_at=deal.assigned_at,
        buyer_chat_id=deal.buyer_chat_id,
        buyer_sender_id=deal.buyer_sender_id,
        seller_contact=deal.sell_order.contact_info if deal.sell_order else None,
        ai_insight=deal.ai_insight,
        ai_resolution=deal.ai_resolution,
        notes=deal.notes,
        target_sell_price=deal.target_sell_price,
        seller_condition=deal.seller_condition,
        seller_city=deal.seller_city,
        seller_specs=deal.seller_specs,
        seller_phone=deal.seller_phone,
        buyer_phone=deal.buyer_phone,
        negotiation_id=deal.negotiation.id if deal.negotiation else None,
        negotiation_stage=deal.negotiation.stage.value if deal.negotiation else None,
        messages_count=msg_count or 0,
    )


@router.get("/{deal_id}/messages")
async def get_deal_messages(
    deal_id: int,
    target: Optional[str] = Query(None, pattern="^(seller|buyer)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Get all messages for a deal (unmasked for owner). Optionally filter by target (seller/buyer)."""
    # Get deal with negotiation
    deal = await db.execute(
        select(DetectedDeal)
        .options(selectinload(DetectedDeal.negotiation))
        .where(DetectedDeal.id == deal_id)
    )
    deal = deal.scalar_one_or_none()

    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )

    if not deal.negotiation:
        return {"messages": [], "seller_messages": [], "buyer_messages": []}

    # Build query
    query = (
        select(NegotiationMessage)
        .options(selectinload(NegotiationMessage.sent_by))
        .where(NegotiationMessage.negotiation_id == deal.negotiation.id)
    )

    if target:
        target_enum = MessageTarget.SELLER if target == "seller" else MessageTarget.BUYER
        query = query.where(NegotiationMessage.target == target_enum)

    query = query.order_by(NegotiationMessage.created_at)

    result = await db.execute(query)
    messages = result.scalars().all()

    all_messages = [
        MessageResponse.from_message(
            msg,
            role="owner",
            sender_name=msg.sent_by.display_name if msg.sent_by else None,
        )
        for msg in messages
    ]

    # If no target filter, also return separated lists
    if not target:
        seller_messages = [m for m in all_messages if m.target == "seller"]
        buyer_messages = [m for m in all_messages if m.target == "buyer"]
        return {
            "messages": all_messages,
            "seller_messages": seller_messages,
            "buyer_messages": buyer_messages,
        }

    return {"messages": all_messages}


@router.post("/{deal_id}/assign")
async def assign_deal(
    request: Request,
    deal_id: int,
    data: DealAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Assign deal to a manager."""
    deal = await db.get(DetectedDeal, deal_id)
    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )

    manager = await db.get(User, data.manager_id)
    if not manager or manager.role != UserRole.MANAGER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid manager",
        )

    if not manager.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manager is inactive",
        )

    deal.manager_id = manager.id
    deal.assigned_at = datetime.now(timezone.utc)
    deal.status = DealStatus.HANDED_TO_MANAGER
    deal.manager_commission_rate = calculate_commission_rate(deal, manager)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.UPDATE_DEAL,
        target_type="deal",
        target_id=deal_id,
        action_metadata={"action": "assign", "manager_id": manager.id, "commission_rate": str(deal.manager_commission_rate)},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True, "manager_name": manager.display_name}


@router.post("/{deal_id}/message")
async def send_message(
    request: Request,
    deal_id: int,
    data: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Send a message as owner to seller or buyer."""
    deal = await db.execute(
        select(DetectedDeal)
        .options(
            selectinload(DetectedDeal.negotiation),
            selectinload(DetectedDeal.buy_order),
        )
        .where(DetectedDeal.id == deal_id)
    )
    deal = deal.scalar_one_or_none()

    if not deal or not deal.negotiation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal or negotiation not found",
        )

    # Determine target
    target_enum = MessageTarget.SELLER if data.target == "seller" else MessageTarget.BUYER

    # Add message to history
    message = NegotiationMessage(
        negotiation_id=deal.negotiation.id,
        role=MessageRole.MANAGER,  # Owner sends as manager role
        target=target_enum,
        content=data.content,
        sent_by_user_id=current_user.id,
    )
    db.add(message)

    # Queue for sending - determine recipient based on target
    if data.target == "seller":
        recipient_id = deal.negotiation.seller_sender_id
    else:
        # Buyer - use buyer_sender_id from deal
        recipient_id = deal.buyer_sender_id
        if not recipient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Buyer contact not available",
            )

    outbox = OutboxMessage(
        recipient_id=recipient_id,
        message_text=data.content,
        negotiation_id=deal.negotiation.id,
        sent_by_user_id=current_user.id,
    )
    db.add(outbox)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.SEND_MESSAGE,
        target_type="negotiation",
        target_id=deal.negotiation.id,
        action_metadata={"target": data.target},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True, "message_id": message.id, "target": data.target}


@router.patch("/{deal_id}/update")
async def update_deal(
    request: Request,
    deal_id: int,
    data: DealUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Update deal parameters (owner only). Auto-recalculates margin."""
    deal = await db.get(DetectedDeal, deal_id)
    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )

    if data.sell_price is not None:
        deal.sell_price = data.sell_price
    if data.buy_price is not None:
        deal.buy_price = data.buy_price
    if data.target_sell_price is not None:
        deal.target_sell_price = data.target_sell_price
    if data.notes is not None:
        deal.notes = data.notes
    if data.region is not None:
        deal.region = data.region
    if data.seller_condition is not None:
        deal.seller_condition = data.seller_condition
    if data.seller_city is not None:
        deal.seller_city = data.seller_city
    if data.seller_specs is not None:
        deal.seller_specs = data.seller_specs

    # Auto-recalculate margin if prices changed
    if data.margin is not None:
        deal.margin = data.margin
    elif data.sell_price is not None or data.buy_price is not None:
        if deal.buy_price and deal.sell_price:
            deal.margin = deal.buy_price - deal.sell_price

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.UPDATE_DEAL,
        target_type="deal",
        target_id=deal_id,
        action_metadata=data.model_dump(exclude_none=True),
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True}


@router.post("/{deal_id}/close")
async def close_deal(
    request: Request,
    deal_id: int,
    data: DealCloseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Close a deal as won or lost."""
    deal = await db.get(DetectedDeal, deal_id)
    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )

    # Update status
    deal.status = DealStatus.WON if data.status == "won" else DealStatus.LOST
    deal.ai_resolution = data.resolution

    # Create ledger entry for won deals
    if deal.status == DealStatus.WON:
        profit = deal.margin
        deal.profit = profit

        # Calculate manager commission using tiered rate
        manager_commission = Decimal("0")
        commission_rate = Decimal("0")
        if deal.manager_id:
            commission_rate = deal.manager_commission_rate or Decimal("0.20")
            manager_commission = deal.margin * commission_rate

        ledger = LedgerEntry(
            deal_id=deal.id,
            buy_amount=deal.buy_price,
            sell_amount=deal.sell_price,
            profit=profit,
            closed_by_user_id=current_user.id,
            manager_commission=manager_commission,
            commission_rate_applied=commission_rate if deal.manager_id else None,
            deal_model=deal.deal_model,
            lead_source=deal.lead_source,
        )
        db.add(ledger)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.CLOSE_DEAL,
        target_type="deal",
        target_id=deal_id,
        action_metadata={"status": data.status, "resolution": data.resolution},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True}


@router.delete("/{deal_id}")
async def delete_deal(
    request: Request,
    deal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Delete a deal and all related data (negotiations, messages, outbox)."""
    deal = await db.get(DetectedDeal, deal_id)
    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )

    # Удаляем связанные данные в правильном порядке (FK constraints)
    negotiation_result = await db.execute(
        select(Negotiation).where(Negotiation.deal_id == deal_id)
    )
    negotiation = negotiation_result.scalar_one_or_none()

    if negotiation:
        # 1. Outbox messages
        await db.execute(
            OutboxMessage.__table__.delete().where(
                OutboxMessage.negotiation_id == negotiation.id
            )
        )
        # 2. Negotiation messages
        await db.execute(
            NegotiationMessage.__table__.delete().where(
                NegotiationMessage.negotiation_id == negotiation.id
            )
        )
        # 3. Negotiation
        await db.delete(negotiation)

    # 4. Деактивируем связанные заказы
    if deal.buy_order_id:
        buy_order = await db.get(Order, deal.buy_order_id)
        if buy_order:
            buy_order.is_active = False
    if deal.sell_order_id:
        sell_order = await db.get(Order, deal.sell_order_id)
        if sell_order:
            sell_order.is_active = False

    # 5. Ledger entries
    await db.execute(
        LedgerEntry.__table__.delete().where(LedgerEntry.deal_id == deal_id)
    )

    # 6. Логируем до удаления (пока deal.product доступен)
    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.DELETE_DEAL,
        target_type="deal",
        target_id=deal_id,
        action_metadata={"product": deal.product},
        ip_address=get_client_ip(request),
    )

    # 6. Удаляем сделку
    await db.delete(deal)

    await db.commit()
    return {"success": True}


# IMPORTANT: This route MUST be after all other /{deal_id}/... routes
# to avoid "data", "messages", etc. being interpreted as deal_id
@router.get("/{deal_id}", response_class=HTMLResponse, include_in_schema=False)
async def deal_detail_page(
    request: Request,
    deal_id: int,
    current_user: User = Depends(require_owner),
):
    """Render deal detail page."""
    return templates.TemplateResponse(
        "admin/deal_detail.html",
        {"request": request, "user": current_user, "deal_id": deal_id},
    )
