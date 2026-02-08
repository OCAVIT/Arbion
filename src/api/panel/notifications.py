"""Manager panel notifications API — unified polling endpoint."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_manager
from src.db import get_db
from src.models import (
    DealStatus,
    DetectedDeal,
    MessageRole,
    MessageTarget,
    Negotiation,
    NegotiationMessage,
    User,
)

router = APIRouter(prefix="/notifications")


class DealUnreadInfo(BaseModel):
    deal_id: int
    negotiation_id: int
    product: str
    unread_seller: int
    unread_buyer: int
    last_message_at: Optional[str] = None
    last_sender_role: Optional[str] = None  # "buyer" or "seller"
    last_message_preview: Optional[str] = None


class NotificationStatusResponse(BaseModel):
    total_unread_messages: int
    deals_with_unread: list[DealUnreadInfo]
    new_leads_count: int
    my_cold_deals_count: int = 0


@router.get("/status", response_model=NotificationStatusResponse)
async def get_notification_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """
    Single polling endpoint for all manager notification data.

    Returns unread message counts per deal and new leads count.
    Only counts messages NOT sent by the manager (role != manager)
    and where read_at IS NULL.
    """
    # Get all active deals for this manager
    deals_result = await db.execute(
        select(DetectedDeal)
        .options(selectinload(DetectedDeal.negotiation))
        .where(
            and_(
                DetectedDeal.manager_id == current_user.id,
                DetectedDeal.status.in_([
                    DealStatus.COLD,
                    DealStatus.IN_PROGRESS,
                    DealStatus.WARM,
                    DealStatus.HANDED_TO_MANAGER,
                ]),
            )
        )
    )
    deals = deals_result.scalars().all()

    deals_with_unread = []
    total_unread = 0

    for deal in deals:
        if not deal.negotiation:
            continue

        neg_id = deal.negotiation.id

        # Count unread seller messages
        unread_seller = await db.scalar(
            select(func.count())
            .select_from(NegotiationMessage)
            .where(
                and_(
                    NegotiationMessage.negotiation_id == neg_id,
                    NegotiationMessage.role != MessageRole.MANAGER,
                    NegotiationMessage.target == MessageTarget.SELLER,
                    NegotiationMessage.read_at.is_(None),
                )
            )
        ) or 0

        # Count unread buyer messages
        unread_buyer = await db.scalar(
            select(func.count())
            .select_from(NegotiationMessage)
            .where(
                and_(
                    NegotiationMessage.negotiation_id == neg_id,
                    NegotiationMessage.role != MessageRole.MANAGER,
                    NegotiationMessage.target == MessageTarget.BUYER,
                    NegotiationMessage.read_at.is_(None),
                )
            )
        ) or 0

        if unread_seller > 0 or unread_buyer > 0:
            # Get latest unread non-manager message for details
            last_msg_result = await db.execute(
                select(NegotiationMessage)
                .where(
                    and_(
                        NegotiationMessage.negotiation_id == neg_id,
                        NegotiationMessage.role != MessageRole.MANAGER,
                        NegotiationMessage.read_at.is_(None),
                    )
                )
                .order_by(NegotiationMessage.created_at.desc())
                .limit(1)
            )
            last_msg = last_msg_result.scalar_one_or_none()

            last_sender_role = None
            last_preview = None
            latest_at = None
            if last_msg:
                if last_msg.role == MessageRole.SELLER:
                    last_sender_role = "seller"
                elif last_msg.role == MessageRole.BUYER:
                    last_sender_role = "buyer"
                last_preview = (last_msg.content or "")[:80]
                latest_at = last_msg.created_at.isoformat() if last_msg.created_at else None

            deals_with_unread.append(DealUnreadInfo(
                deal_id=deal.id,
                negotiation_id=neg_id,
                product=deal.product,
                unread_seller=unread_seller,
                unread_buyer=unread_buyer,
                last_message_at=latest_at,
                last_sender_role=last_sender_role,
                last_message_preview=last_preview,
            ))
            total_unread += unread_seller + unread_buyer

    # Count new leads (unassigned COLD/WARM)
    new_leads = await db.scalar(
        select(func.count())
        .select_from(DetectedDeal)
        .where(
            and_(
                DetectedDeal.manager_id.is_(None),
                DetectedDeal.status.in_([DealStatus.COLD, DealStatus.WARM]),
            )
        )
    ) or 0

    # Count cold deals assigned to this manager (for real-time cold deal alerts)
    my_cold = await db.scalar(
        select(func.count())
        .select_from(DetectedDeal)
        .where(
            and_(
                DetectedDeal.manager_id == current_user.id,
                DetectedDeal.status == DealStatus.COLD,
            )
        )
    ) or 0

    return NotificationStatusResponse(
        total_unread_messages=total_unread,
        deals_with_unread=deals_with_unread,
        new_leads_count=new_leads,
        my_cold_deals_count=my_cold,
    )
