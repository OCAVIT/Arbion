"""Manager panel chat API endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_manager
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
    NegotiationStage,
    OutboxMessage,
    User,
)
from src.schemas.deal import DealCloseRequest, MessageResponse, SendMessageRequest
from src.utils.audit import get_client_ip, log_action

router = APIRouter(prefix="/chat")
templates = Jinja2Templates(directory="src/templates")


@router.get("/{negotiation_id}", response_class=HTMLResponse, include_in_schema=False)
async def chat_page(
    request: Request,
    negotiation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Render chat page for a negotiation.

    SECURITY: Verifies manager has access to this deal.
    """
    # Get negotiation with deal
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Переговоры не найдены",
        )

    # SECURITY CHECK: Manager can only access their assigned deals
    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой сделке",
        )

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.VIEW_DEAL,
        target_type="negotiation",
        target_id=negotiation_id,
        ip_address=get_client_ip(request),
    )

    return templates.TemplateResponse(
        "panel/chat.html",
        {
            "request": request,
            "user": current_user,
            "negotiation_id": negotiation_id,
            "deal": negotiation.deal,
        },
    )


@router.get("/{negotiation_id}/messages")
async def get_messages(
    negotiation_id: int,
    target: Optional[str] = Query(None, pattern="^(seller|buyer)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Get chat messages for a negotiation.

    SECURITY:
    - Verifies manager has access
    - Masks sensitive data (phones, usernames) in messages
    """
    # Get negotiation with deal
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Переговоры не найдены",
        )

    # SECURITY CHECK
    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой сделке",
        )

    # Build query
    query = (
        select(NegotiationMessage)
        .options(selectinload(NegotiationMessage.sent_by))
        .where(NegotiationMessage.negotiation_id == negotiation_id)
    )

    if target:
        target_enum = MessageTarget.SELLER if target == "seller" else MessageTarget.BUYER
        query = query.where(NegotiationMessage.target == target_enum)

    query = query.order_by(NegotiationMessage.created_at)

    msg_result = await db.execute(query)
    messages = msg_result.scalars().all()

    all_messages = [
        MessageResponse.from_message(
            msg,
            role="manager",  # This triggers masking
            sender_name=msg.sent_by.display_name if msg.sent_by else None,
        )
        for msg in messages
    ]

    # If no target filter, return separated lists
    if not target:
        seller_messages = [m for m in all_messages if m.target == "seller"]
        buyer_messages = [m for m in all_messages if m.target == "buyer"]
        return {
            "messages": all_messages,
            "seller_messages": seller_messages,
            "buyer_messages": buyer_messages,
            "deal_status": negotiation.deal.status.value,
            "product": negotiation.deal.product,
            "sell_price": str(negotiation.deal.sell_price),
        }

    return {
        "messages": all_messages,
        "deal_status": negotiation.deal.status.value,
        "product": negotiation.deal.product,
        "sell_price": str(negotiation.deal.sell_price),
    }


@router.post("/{negotiation_id}/send")
async def send_message(
    request: Request,
    negotiation_id: int,
    data: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Send a message in the negotiation to seller or buyer.

    Message is queued for sending via Telegram.
    """
    # Get negotiation with deal
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Переговоры не найдены",
        )

    # SECURITY CHECK
    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой сделке",
        )

    # Check deal is not closed
    if negotiation.deal.status in [DealStatus.WON, DealStatus.LOST]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сделка уже закрыта",
        )

    # Determine target
    target_enum = MessageTarget.SELLER if data.target == "seller" else MessageTarget.BUYER

    # Add message to history
    message = NegotiationMessage(
        negotiation_id=negotiation_id,
        role=MessageRole.MANAGER,
        target=target_enum,
        content=data.content,
        sent_by_user_id=current_user.id,
    )
    db.add(message)

    # Determine recipient based on target
    if data.target == "seller":
        recipient_id = negotiation.seller_sender_id
    else:
        # Buyer - use buyer_sender_id from deal
        recipient_id = negotiation.deal.buyer_sender_id
        if not recipient_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Контакт покупателя недоступен",
            )

    # Queue for sending via Telegram
    outbox = OutboxMessage(
        recipient_id=recipient_id,
        message_text=data.content,
        negotiation_id=negotiation_id,
        sent_by_user_id=current_user.id,
    )
    db.add(outbox)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.SEND_MESSAGE,
        target_type="negotiation",
        target_id=negotiation_id,
        ip_address=get_client_ip(request),
    )

    await db.commit()
    await db.refresh(message)

    return {
        "success": True,
        "message_id": message.id,
        "message": MessageResponse.from_message(
            message,
            role="manager",
            sender_name=current_user.display_name,
        ),
    }


@router.post("/{negotiation_id}/close")
async def close_deal(
    request: Request,
    negotiation_id: int,
    data: DealCloseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Close a deal as won or lost.

    SECURITY: Manager cannot see profit - ledger entry is created
    by the system/owner.
    """
    # Get negotiation with deal
    result = await db.execute(
        select(Negotiation)
        .options(selectinload(Negotiation.deal))
        .where(Negotiation.id == negotiation_id)
    )
    negotiation = result.scalar_one_or_none()

    if not negotiation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Переговоры не найдены",
        )

    # SECURITY CHECK
    if negotiation.deal.manager_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="У вас нет доступа к этой сделке",
        )

    deal = negotiation.deal

    # Check deal is not already closed
    if deal.status in [DealStatus.WON, DealStatus.LOST]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сделка уже закрыта",
        )

    # Update status
    deal.status = DealStatus.WON if data.status == "won" else DealStatus.LOST
    deal.ai_resolution = data.resolution

    # Update negotiation stage
    negotiation.stage = NegotiationStage.CLOSED

    # Create ledger entry for won deals
    # Note: Profit calculation - manager doesn't see this
    if deal.status == DealStatus.WON:
        profit = deal.margin
        deal.profit = profit

        ledger = LedgerEntry(
            deal_id=deal.id,
            buy_amount=deal.buy_price,
            sell_amount=deal.sell_price,
            profit=profit,
            closed_by_user_id=current_user.id,
        )
        db.add(ledger)

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.CLOSE_DEAL,
        target_type="deal",
        target_id=deal.id,
        action_metadata={"status": data.status, "resolution": data.resolution},
        ip_address=get_client_ip(request),
    )

    await db.commit()

    return {
        "success": True,
        "message": "Сделка закрыта" if data.status == "won" else "Сделка отменена",
    }
