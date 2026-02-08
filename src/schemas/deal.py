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
from src.models.negotiation import MessageRole, MessageTarget
from src.utils.masking import generate_contact_ref, mask_sensitive


class DealUpdateRequest(BaseModel):
    """Request to update deal parameters (owner only)."""

    sell_price: Optional[Decimal] = None
    buy_price: Optional[Decimal] = None
    target_sell_price: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    notes: Optional[str] = Field(None, max_length=2000)
    region: Optional[str] = Field(None, max_length=100)
    seller_condition: Optional[str] = Field(None, max_length=500)
    seller_city: Optional[str] = Field(None, max_length=100)
    seller_specs: Optional[str] = Field(None, max_length=500)


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

    # Deal details
    notes: Optional[str] = None
    target_sell_price: Optional[Decimal] = None
    seller_condition: Optional[str] = None
    seller_city: Optional[str] = None
    seller_specs: Optional[str] = None
    seller_phone: Optional[str] = None
    buyer_phone: Optional[str] = None

    # Negotiation info
    negotiation_id: Optional[int]
    negotiation_stage: Optional[str]
    messages_count: int = 0

    # Strategic update fields (Section 6)
    lead_source: Optional[str] = None
    niche: Optional[str] = None
    deal_model: str = "agency"
    manager_commission_rate: Optional[float] = None
    buyer_payment_status: str = "pending"
    seller_payment_status: str = "pending"
    our_commission_status: str = "pending"
    payment_method: Optional[str] = None
    ai_draft_message: Optional[str] = None
    market_price_context: Optional[str] = None  # JSON string
    platform: str = "telegram"

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

    # Commission (only for closed WON deals)
    commission: Optional[Decimal] = None

    # Strategic update fields (Section 6)
    lead_source: Optional[str] = None
    niche: Optional[str] = None
    ai_draft_message: Optional[str] = None
    market_price_context: Optional[str] = None  # Manager sees market context
    platform: str = "telegram"

    # Seller city (from sell order region)
    seller_city: Optional[str] = None

    # Volume info from linked order
    volume: Optional[str] = None  # e.g. "20 тонна", "500 м²"
    unit: Optional[str] = None

    # Buyer volume/region (for lead card display)
    buyer_volume: Optional[str] = None
    buyer_region: Optional[str] = None

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
        commission: Optional[Decimal] = None,
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

        # Extract volume from sell_order
        volume_str = None
        unit_str = None
        sell_order = getattr(deal, 'sell_order', None)
        if sell_order:
            vol = getattr(sell_order, 'volume_numeric', None)
            unit_str = getattr(sell_order, 'unit', None)
            if vol is not None and unit_str:
                vol_num = float(vol)
                volume_str = f"{int(vol_num) if vol_num == int(vol_num) else vol_num} {unit_str}"

        # Extract buyer volume/region from buy_order
        buyer_volume_str = None
        buyer_region_str = deal.region  # deal.region = buyer's region
        buy_order = getattr(deal, 'buy_order', None)
        if buy_order:
            bvol = getattr(buy_order, 'volume_numeric', None)
            bunit = getattr(buy_order, 'unit', None)
            if bvol is not None and bunit:
                bvol_num = float(bvol)
                buyer_volume_str = f"{int(bvol_num) if bvol_num == int(bvol_num) else bvol_num} {bunit}"
            if not buyer_region_str:
                buyer_region_str = getattr(buy_order, 'region', None)

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
            commission=commission,
            lead_source=getattr(deal, 'lead_source', None),
            niche=getattr(deal, 'niche', None),
            ai_draft_message=getattr(deal, 'ai_draft_message', None),
            market_price_context=getattr(deal, 'market_price_context', None),
            platform=getattr(deal, 'platform', 'telegram'),
            seller_city=getattr(deal, 'seller_city', None),
            volume=volume_str,
            unit=unit_str,
            buyer_volume=buyer_volume_str,
            buyer_region=buyer_region_str,
        )


class MessageResponse(BaseModel):
    """Chat message for display."""

    id: int
    role: str  # "ai", "seller", "buyer", "manager"
    target: str  # "seller" or "buyer" - which chat this message belongs to
    content: str
    sender_name: Optional[str]
    created_at: datetime
    media_type: Optional[str] = None  # "photo", "video", "document", "sticker"
    file_name: Optional[str] = None  # Original filename for documents
    telegram_message_id: Optional[int] = None  # This message's Telegram ID
    reply_to_message_id: Optional[int] = None  # Telegram msg ID this replies to
    reply_to_content: Optional[str] = None  # Truncated content of replied message
    reply_to_sender_name: Optional[str] = None  # Who sent the replied message
    read_at: Optional[datetime] = None  # When manager read this (NULL = unread)

    model_config = {"from_attributes": True}

    @classmethod
    def from_message(
        cls,
        message,
        role: str,
        sender_name: Optional[str] = None,
        reply_info: Optional[dict] = None,
    ) -> "MessageResponse":
        """
        Create response from message model.

        Args:
            message: NegotiationMessage model
            role: User role for masking ("owner" or "manager")
            sender_name: Display name for the sender
            reply_info: Optional dict with reply_to_content and reply_to_sender_name

        For managers, sensitive content is masked.
        """
        content = mask_sensitive(message.content, role)

        # Determine display name
        if message.role == MessageRole.AI:
            display_name = "Ассистент"
        elif message.role == MessageRole.SELLER:
            display_name = "Продавец"
        elif message.role == MessageRole.BUYER:
            display_name = "Покупатель"
        elif message.role == MessageRole.MANAGER:
            display_name = sender_name or "Менеджер"
        else:
            display_name = "Система"

        # Get target value
        target_value = message.target.value if hasattr(message, 'target') and message.target else "seller"

        return cls(
            id=message.id,
            role=message.role,
            target=target_value,
            content=content,
            sender_name=display_name,
            created_at=message.created_at,
            media_type=getattr(message, 'media_type', None),
            file_name=getattr(message, 'file_name', None),
            telegram_message_id=getattr(message, 'telegram_message_id', None),
            reply_to_message_id=getattr(message, 'reply_to_message_id', None),
            reply_to_content=reply_info.get('content') if reply_info else None,
            reply_to_sender_name=reply_info.get('sender_name') if reply_info else None,
            read_at=getattr(message, 'read_at', None),
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
    target: str = Field(
        default="seller",
        pattern="^(seller|buyer)$",
        description="Target chat: seller or buyer"
    )
    reply_to_msg_id: Optional[int] = Field(
        None,
        description="NegotiationMessage ID to reply to (resolved to telegram_message_id)"
    )


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
