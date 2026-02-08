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


class NotificationStatusResponse(BaseModel):
    total_unread_messages: int
    deals_with_unread: list[DealUnreadInfo]
    new_leads_count: int


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
            latest = await db.scalar(
                select(func.max(NegotiationMessage.created_at))
                .where(
                    and_(
                        NegotiationMessage.negotiation_id == neg_id,
                        NegotiationMessage.role != MessageRole.MANAGER,
                        NegotiationMessage.read_at.is_(None),
                    )
                )
            )
            deals_with_unread.append(DealUnreadInfo(
                deal_id=deal.id,
                negotiation_id=neg_id,
                product=deal.product,
                unread_seller=unread_seller,
                unread_buyer=unread_buyer,
                last_message_at=latest.isoformat() if latest else None,
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

    return NotificationStatusResponse(
        total_unread_messages=total_unread,
        deals_with_unread=deals_with_unread,
        new_leads_count=new_leads,
    )
