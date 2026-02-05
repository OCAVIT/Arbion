"""
Deal schemas with role-based data exposure.

CRITICAL SECURITY:
- OwnerDealResponse: All financial data visible
- ManagerDealResponse: NO buy_price, margin, profit, buyer_*
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field

from src.models.deal import DealStatus
from src.models.negotiation import MessageRole
from src.utils.masking import generate_contact_ref, mask_sensitive


class OwnerDealResponse(BaseModel):
    """
    Full deal information for owner.

    Includes all financial data and buyer information.
    """

    id: int
    product: str
    region: Optional[str]

    # Financial data (OWNER ONLY)
    buy_price: Decimal
    sell_price: Decimal
    margin: Decimal
    profit: Optional[Decimal]

    # Status
    status: DealStatus
    created_at: datetime
    updated_at: Optional[datetime]

    # Manager assignment
    manager_id: Optional[int]
    manager_name: Optional[str]
    assigned_at: Optional[datetime]

    # Buyer info (OWNER ONLY)
    buyer_chat_id: Optional[int]
    buyer_sender_id: Optional[int]

    # Seller contact (full)
    seller_contact: Optional[str]

    # AI insights
    ai_insight: Optional[str]
    ai_resolution: Optional[str]

    # Negotiation info
    negotiation_id: Optional[int]
    negotiation_stage: Optional[str]
    messages_count: int = 0

    model_config = {"from_attributes": True}


class ManagerDealResponse(BaseModel):
    """
    Limited deal information for manager.

    SECURITY: Does NOT include:
    - buy_price
    - margin
    - profit
    - buyer_chat_id
    - buyer_sender_id

    Seller contact is ONLY shown when deal status is HANDED_TO_MANAGER
    (i.e., when the manager has taken the deal into work).
    """

    id: int
    product: str
    region: Optional[str]

    # Only sell_price visible to manager
    sell_price: Decimal = Field(
        ...,
        description="Requested price from seller",
    )

    # Status
    status: DealStatus
    created_at: datetime

    # Contact reference (hashed, not real contact)
    contact_ref: str = Field(
        ...,
        description="Anonymous seller reference",
    )

    # Seller contact - ONLY visible when status is HANDED_TO_MANAGER
    # This is the phone number/contact for the manager to reach the seller
    seller_contact: Optional[str] = Field(
        None,
        description="Seller contact info (only visible after taking the deal)",
    )

    # Negotiation info
    negotiation_id: Optional[int]
    negotiation_stage: Optional[str]
    messages_count: int = 0

    # Can manager take this deal?
    can_take: bool = True
    take_blocked_reason: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_deal(
        cls,
        deal,
        negotiation=None,
        messages_count: int = 0,
        can_take: bool = True,
        take_blocked_reason: Optional[str] = None,
        seller_contact: Optional[str] = None,
    ) -> "ManagerDealResponse":
        """
        Create manager response from deal model.

        Handles all masking and data filtering.

        Args:
            deal: DetectedDeal model
            negotiation: Optional Negotiation model
            messages_count: Number of messages in negotiation
            can_take: Whether the manager can take this deal
            take_blocked_reason: Reason why taking is blocked
            seller_contact: Contact info from sell_order (only passed when
                           deal status is HANDED_TO_MANAGER and manager owns the deal)
        """
        # Generate anonymous contact reference
        seller_chat_id = negotiation.seller_chat_id if negotiation else 0
        seller_sender_id = negotiation.seller_sender_id if negotiation else 0
        contact_ref = generate_contact_ref(seller_sender_id, seller_chat_id)

        # Only include seller_contact if deal is handed to manager
        # This is an additional security check
        actual_contact = None
        if deal.status == DealStatus.HANDED_TO_MANAGER and seller_contact:
            actual_contact = seller_contact

        return cls(
            id=deal.id,
            product=deal.product,
            region=deal.region,
            sell_price=deal.sell_price,
            status=deal.status,
            created_at=deal.created_at,
            contact_ref=contact_ref,
            seller_contact=actual_contact,
            negotiation_id=negotiation.id if negotiation else None,
            negotiation_stage=negotiation.stage.value if negotiation else None,
            messages_count=messages_count,
            can_take=can_take,
            take_blocked_reason=take_blocked_reason,
        )


class MessageResponse(BaseModel):
    """Chat message for display."""

    id: int
    role: str  # "ai", "seller", "manager"
    content: str
    sender_name: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_message(
        cls,
        message,
        role: str,
        sender_name: Optional[str] = None,
    ) -> "MessageResponse":
        """
        Create response from message model.

        Args:
            message: NegotiationMessage model
            role: User role for masking ("owner" or "manager")
            sender_name: Display name for the sender

        For managers, sensitive content is masked.
        """
        content = mask_sensitive(message.content, role)

        # Determine display name
        if message.role == MessageRole.AI:
            display_name = "Ассистент"
        elif message.role == MessageRole.SELLER:
            display_name = "Продавец"
        elif message.role == MessageRole.MANAGER:
            display_name = sender_name or "Менеджер"
        else:
            display_name = "Система"

        return cls(
            id=message.id,
            role=message.role,
            content=content,
            sender_name=display_name,
            created_at=message.created_at,
        )


class DealAssignRequest(BaseModel):
    """Request to assign deal to manager."""

    manager_id: int


class DealCloseRequest(BaseModel):
    """Request to close a deal."""

    status: str = Field(..., pattern="^(won|lost)$")
    resolution: Optional[str] = Field(None, max_length=1000)


class SendMessageRequest(BaseModel):
    """Request to send a message in negotiation."""

    content: str = Field(..., min_length=1, max_length=4000)


class DealListResponse(BaseModel):
    """Paginated list of deals."""

    items: List[OwnerDealResponse]
    total: int
    page: int
    per_page: int
    pages: int


class ManagerDealListResponse(BaseModel):
    """Paginated list of deals for manager."""

    items: List[ManagerDealResponse]
    total: int
    page: int
    per_page: int
    pages: int
