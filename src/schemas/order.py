"""Order schemas."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.order import OrderType


class OrderCreate(BaseModel):
    """Create order (usually done by parser)."""

    order_type: OrderType
    chat_id: int
    sender_id: int
    message_id: int
    product: str = Field(..., max_length=255)
    price: Optional[Decimal] = None
    quantity: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)
    raw_text: str
    contact_info: Optional[str] = Field(None, max_length=255)


class OrderUpdate(BaseModel):
    """Update order."""

    is_active: Optional[bool] = None
    price: Optional[Decimal] = None
    region: Optional[str] = Field(None, max_length=100)


class OrderResponse(BaseModel):
    """Order information for admin view."""

    id: int
    order_type: OrderType
    chat_id: int
    sender_id: int
    message_id: int
    product: str
    price: Optional[Decimal]
    quantity: Optional[str]
    region: Optional[str]
    raw_text: str
    contact_info: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    # Related info
    chat_title: Optional[str] = None

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    """Paginated list of orders."""

    items: List[OrderResponse]
    total: int
    page: int
    per_page: int
    pages: int


class OrderStatsResponse(BaseModel):
    """Order statistics."""

    total_orders: int
    buy_orders: int
    sell_orders: int
    active_orders: int
    orders_today: int
