"""Manager panel leads API endpoints.

New endpoints for Section 7:
- GET  /leads/{deal_id}/card   — Lead card with AI analytics
- POST /leads/{deal_id}/send-draft — Send or edit AI draft
- POST /leads/{deal_id}/skip   — Skip a lead
- POST /leads/create           — Manager creates own lead
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_manager
from src.db import get_db
from src.models import (
    AuditAction,
    DealStatus,
    DetectedDeal,
    Negotiation,
    NegotiationStage,
    Order,
    OrderType,
    OutboxMessage,
    User,
)
from src.schemas.copilot import LeadCardResponse
from src.services.ai_copilot import copilot
from src.services.commission import calculate_commission_rate
from src.utils.audit import get_client_ip, log_action

router = APIRouter(prefix="/leads")


# ── Request schemas ──────────────────────────────────────


class SendDraftRequest(BaseModel):
    """Request to send (or edit) AI draft message."""

    message: str = Field(..., min_length=1, max_length=4000)
    target: str = Field(default="seller", pattern="^(seller|buyer)$")


class SkipLeadRequest(BaseModel):
    """Request to skip a lead."""

    reason: str = Field(
        ...,
        pattern="^(low_margin|bad_product|no_contact|other)$",
    )


class CreateLeadRequest(BaseModel):
    """Manager creates own lead (lead_source=manager)."""

    product: str = Field(..., min_length=1, max_length=255)
    niche: Optional[str] = Field(None, pattern="^(construction|agriculture|fmcg|other)$")
    sell_price: Decimal = Field(..., gt=0)
    buy_price: Optional[Decimal] = Field(None, gt=0)
    region: Optional[str] = Field(None, max_length=100)
    seller_city: Optional[str] = Field(None, max_length=100)
    volume: Optional[str] = Field(None, max_length=100)
    contact_info: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=2000)


# ── Endpoints ────────────────────────────────────────────


@router.get("/{deal_id}/card", response_model=LeadCardResponse)
async def get_lead_card(
    deal_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Get lead card with AI analytics for manager."""
    result = await db.execute(
        select(DetectedDeal)
        .options(
            selectinload(DetectedDeal.sell_order),
            selectinload(DetectedDeal.buy_order),
        )
        .where(DetectedDeal.id == deal_id)
    )
    deal = result.scalar_one_or_none()

    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Лид не найден",
        )

    # Manager can see: their own deals + unassigned COLD/WARM deals
    if deal.manager_id is not None and deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этому лиду",
        )

    # Calculate estimated margin as percentage (without revealing buy_price)
    estimated_margin = 0.0
    if deal.margin and deal.sell_price and deal.sell_price > 0:
        estimated_margin = round(
            float(deal.margin / deal.sell_price * 100), 1
        )

    # Parse market context
    market_context = None
    if deal.market_price_context:
        try:
            market_context = json.loads(deal.market_price_context)
        except (json.JSONDecodeError, TypeError):
            pass

    # Get volume from sell order
    volume = None
    if deal.sell_order and deal.sell_order.quantity:
        volume = deal.sell_order.quantity

    return LeadCardResponse(
        deal_id=deal.id,
        product=deal.product,
        niche=deal.niche,
        sell_price=float(deal.sell_price),
        estimated_margin=estimated_margin,
        volume=volume,
        region=deal.region,
        seller_city=deal.seller_city,
        ai_draft_message=deal.ai_draft_message,
        market_context=market_context,
        created_at=deal.created_at,
        platform=deal.platform,
    )


@router.post("/{deal_id}/send-draft")
async def send_draft(
    request: Request,
    deal_id: int,
    data: SendDraftRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Manager sends AI draft (possibly edited) to seller or buyer.

    If the deal isn't assigned yet, assigns it to this manager.
    Creates a Negotiation if none exists, then queues the message.
    """
    result = await db.execute(
        select(DetectedDeal)
        .options(
            selectinload(DetectedDeal.negotiation),
            selectinload(DetectedDeal.sell_order),
        )
        .where(DetectedDeal.id == deal_id)
    )
    deal = result.scalar_one_or_none()

    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Лид не найден",
        )

    # Check access: unassigned or assigned to this manager
    if deal.manager_id is not None and deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Лид назначен другому менеджеру",
        )

    # Check deal is not closed
    if deal.status in (DealStatus.WON, DealStatus.LOST):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сделка уже закрыта",
        )

    # Auto-assign if not yet assigned
    if deal.manager_id is None:
        deal.manager_id = current_user.id
        deal.assigned_at = datetime.now(timezone.utc)
        deal.manager_commission_rate = calculate_commission_rate(deal, current_user)

    deal.status = DealStatus.HANDED_TO_MANAGER

    # Determine recipient
    if data.target == "seller":
        if not deal.sell_order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Контакт продавца недоступен",
            )
        recipient_id = deal.sell_order.sender_id
    else:
        if not deal.buyer_sender_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Контакт покупателя недоступен",
            )
        recipient_id = deal.buyer_sender_id

    # Create negotiation if doesn't exist
    negotiation = deal.negotiation
    if not negotiation:
        negotiation = Negotiation(
            deal_id=deal.id,
            seller_chat_id=deal.sell_order.chat_id if deal.sell_order else 0,
            seller_sender_id=deal.sell_order.sender_id if deal.sell_order else 0,
            stage=NegotiationStage.INITIAL,
        )
        db.add(negotiation)
        await db.flush()

    # Queue message for sending via Telegram
    outbox = OutboxMessage(
        recipient_id=recipient_id,
        message_text=data.message,
        negotiation_id=negotiation.id,
        sent_by_user_id=current_user.id,
    )
    db.add(outbox)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.SEND_DRAFT,
        target_type="deal",
        target_id=deal_id,
        action_metadata={"target": data.target, "message_length": len(data.message)},
        ip_address=get_client_ip(request),
    )

    await db.commit()

    return {"success": True, "message": "Драфт отправлен"}


@router.post("/{deal_id}/skip")
async def skip_lead(
    request: Request,
    deal_id: int,
    data: SkipLeadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Manager skips a lead with a reason."""
    deal = await db.get(DetectedDeal, deal_id)

    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Лид не найден",
        )

    # Can skip: unassigned deals or own deals
    if deal.manager_id is not None and deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Лид назначен другому менеджеру",
        )

    # Already closed
    if deal.status in (DealStatus.WON, DealStatus.LOST):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сделка уже закрыта",
        )

    deal.status = DealStatus.LOST
    deal.ai_resolution = f"Пропущен менеджером: {data.reason}"

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.SKIP_LEAD,
        target_type="deal",
        target_id=deal_id,
        action_metadata={"reason": data.reason},
        ip_address=get_client_ip(request),
    )

    await db.commit()

    return {"success": True, "message": "Лид пропущен"}


@router.post("/create")
async def create_lead(
    request: Request,
    data: CreateLeadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Manager creates their own lead (lead_source=manager).

    Creates a synthetic sell order and a DetectedDeal.
    Commission tier: 35% (manager lead).
    """
    # Create a synthetic sell order for the deal
    sell_order = Order(
        order_type=OrderType.SELL,
        chat_id=0,
        sender_id=0,
        message_id=0,
        product=data.product,
        price=data.sell_price,
        quantity=data.volume,
        region=data.region,
        raw_text=f"[Лид менеджера] {data.product}",
        contact_info=data.contact_info,
        platform="manual",
        niche=data.niche,
    )
    db.add(sell_order)

    # Also create a synthetic buy order (manager knows the buyer)
    buy_price = data.buy_price or data.sell_price
    buy_order = Order(
        order_type=OrderType.BUY,
        chat_id=0,
        sender_id=0,
        message_id=0,
        product=data.product,
        price=buy_price,
        region=data.region,
        raw_text=f"[Лид менеджера] {data.product}",
        platform="manual",
        niche=data.niche,
    )
    db.add(buy_order)
    await db.flush()

    # Calculate margin
    margin = buy_price - data.sell_price

    # Create deal
    deal = DetectedDeal(
        buy_order_id=buy_order.id,
        sell_order_id=sell_order.id,
        product=data.product,
        region=data.region,
        buy_price=buy_price,
        sell_price=data.sell_price,
        margin=margin,
        status=DealStatus.HANDED_TO_MANAGER,
        manager_id=current_user.id,
        assigned_at=datetime.now(timezone.utc),
        lead_source="manager",
        niche=data.niche,
        deal_model="agency",
        platform="manual",
        notes=data.notes,
        seller_city=data.seller_city,
        manager_commission_rate=calculate_commission_rate(
            # Use a namespace to pass lead_source before the deal exists
            type("_D", (), {"lead_source": "manager"})(),
            current_user,
        ),
    )
    db.add(deal)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.CREATE_LEAD,
        target_type="deal",
        target_id=0,
        action_metadata={"product": data.product, "niche": data.niche},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    await db.refresh(deal)

    return {
        "success": True,
        "deal_id": deal.id,
        "message": "Лид создан",
    }
