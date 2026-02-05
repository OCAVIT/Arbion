"""User and manager schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ManagerCreate(BaseModel):
    """Create a new manager account."""

    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=100)


class ManagerUpdate(BaseModel):
    """Update manager account."""

    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None


class ManagerResponse(BaseModel):
    """Manager information for admin view."""

    id: int
    username: str
    display_name: str
    is_active: bool
    created_at: datetime
    last_active_at: Optional[datetime]

    # Unique invite token for personal login link
    invite_token: Optional[str] = None

    # Stats
    active_deals_count: int = 0
    won_deals_count: int = 0
    lost_deals_count: int = 0
    conversion_rate: float = 0.0
    avg_deal_value: Decimal = Decimal("0.00")

    model_config = {"from_attributes": True}


class ManagerStatsResponse(BaseModel):
    """Detailed manager statistics."""

    id: int
    display_name: str

    # Deal counts
    total_deals: int
    active_deals: int
    won_deals: int
    lost_deals: int

    # Performance
    conversion_rate: float
    avg_close_time_hours: Optional[float]
    avg_profit: Decimal = Decimal("0.00")
    total_profit: Decimal = Decimal("0.00")

    # Activity
    messages_sent: int
    last_active_at: Optional[datetime]


class ProfileResponse(BaseModel):
    """User profile for panel view."""

    id: int
    username: str
    display_name: str
    role: str
    created_at: datetime
    last_active_at: Optional[datetime]

    # Personal stats (for managers)
    active_deals_count: int = 0
    closed_deals_month: int = 0
    conversion_rate: float = 0.0

    model_config = {"from_attributes": True}


class PasswordChange(BaseModel):
    """Password change request."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=100)
