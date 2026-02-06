"""Dashboard metrics schemas."""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MetricsResponse(BaseModel):
    """Main dashboard metrics."""

    # Chats
    total_chats: int
    target_chats: int
    active_chats: int

    # Messages
    messages_today: int
    messages_filtered: int
    filter_rate: float  # percentage

    # Orders
    active_buy_orders: int
    active_sell_orders: int
    orders_today: int

    # Deals by status
    deals_cold: int
    deals_in_progress: int
    deals_warm: int
    deals_with_manager: int
    deals_won: int
    deals_lost: int

    # Profit
    profit_today: Decimal
    profit_week: Decimal
    profit_month: Decimal

    # Conversion funnel
    funnel_messages: int
    funnel_orders: int
    funnel_deals: int
    funnel_closed: int


class ChartDataPoint(BaseModel):
    """Single data point for charts."""

    label: str
    value: float


class OrdersChartResponse(BaseModel):
    """Orders by day chart data."""

    labels: List[str]  # Dates
    buy_orders: List[int]
    sell_orders: List[int]


class MarginChartResponse(BaseModel):
    """Margin by category chart data."""

    categories: List[str]
    margins: List[Decimal]


class FunnelChartResponse(BaseModel):
    """Conversion funnel chart data."""

    stages: List[str]
    values: List[int]
    percentages: List[float]


class ManagerPanelStatsResponse(BaseModel):
    """Stats for manager panel dashboard."""

    active_deals: int
    closed_this_month: int
    conversion_rate: float
    warm_leads_in_pool: int
    total_earned: Decimal = Decimal("0.00")


class LedgerEntryResponse(BaseModel):
    """Financial ledger entry."""

    id: int
    deal_id: int
    product: str
    buy_amount: Decimal
    sell_amount: Decimal
    profit: Decimal
    closed_by: str
    closed_at: datetime


class LedgerSummaryResponse(BaseModel):
    """Financial summary."""

    total_profit: Decimal
    total_deals: int
    avg_profit_per_deal: Decimal
    profit_by_period: Dict[str, Decimal]


class AuditLogResponse(BaseModel):
    """Audit log entry for admin view."""

    id: int
    user_id: int
    username: str
    display_name: str
    action: str
    target_type: Optional[str]
    target_id: Optional[int]
    metadata: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Paginated audit log."""

    items: List[AuditLogResponse]
    total: int
    page: int
    per_page: int
    pages: int
