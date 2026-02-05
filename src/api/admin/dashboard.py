"""Admin dashboard API endpoints."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_owner
from src.db import get_db
from src.models import (
    DealStatus,
    DetectedDeal,
    LedgerEntry,
    MonitoredChat,
    Order,
    OrderType,
    RawMessage,
    SystemSetting,
    User,
)
from src.schemas.dashboard import MetricsResponse

router = APIRouter()
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard_page(
    request: Request,
    current_user: User = Depends(require_owner),
):
    """Render admin dashboard page."""
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "user": current_user},
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """
    Get dashboard metrics.

    Called by frontend every 15 seconds for live updates.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start.replace(day=1)

    # Chat counts
    chat_counts = await db.execute(
        select(
            func.count().filter(MonitoredChat.status == "active").label("active"),
            func.count().label("total"),
        ).select_from(MonitoredChat)
    )
    chat_row = chat_counts.one()

    # Get target from settings
    target_setting = await db.get(SystemSetting, "target_chat_count")
    target_chats = target_setting.get_value() if target_setting else 100

    # Messages today
    msg_counts = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(RawMessage.processed == True).label("processed"),
        )
        .select_from(RawMessage)
        .where(RawMessage.created_at >= today_start)
    )
    msg_row = msg_counts.one()
    filter_rate = (msg_row.processed / msg_row.total * 100) if msg_row.total > 0 else 0

    # Order counts
    order_counts = await db.execute(
        select(
            func.count()
            .filter(and_(Order.order_type == OrderType.BUY, Order.is_active == True))
            .label("buy"),
            func.count()
            .filter(and_(Order.order_type == OrderType.SELL, Order.is_active == True))
            .label("sell"),
            func.count().filter(Order.created_at >= today_start).label("today"),
        ).select_from(Order)
    )
    order_row = order_counts.one()

    # Deal counts by status
    deal_counts = await db.execute(
        select(
            func.count().filter(DetectedDeal.status == DealStatus.COLD).label("cold"),
            func.count()
            .filter(DetectedDeal.status == DealStatus.IN_PROGRESS)
            .label("in_progress"),
            func.count().filter(DetectedDeal.status == DealStatus.WARM).label("warm"),
            func.count()
            .filter(DetectedDeal.status == DealStatus.HANDED_TO_MANAGER)
            .label("with_manager"),
            func.count().filter(DetectedDeal.status == DealStatus.WON).label("won"),
            func.count().filter(DetectedDeal.status == DealStatus.LOST).label("lost"),
        ).select_from(DetectedDeal)
    )
    deal_row = deal_counts.one()

    # Profit calculations
    profit_today = await db.execute(
        select(func.coalesce(func.sum(LedgerEntry.profit), Decimal("0")))
        .select_from(LedgerEntry)
        .where(LedgerEntry.closed_at >= today_start)
    )
    profit_week = await db.execute(
        select(func.coalesce(func.sum(LedgerEntry.profit), Decimal("0")))
        .select_from(LedgerEntry)
        .where(LedgerEntry.closed_at >= week_start)
    )
    profit_month = await db.execute(
        select(func.coalesce(func.sum(LedgerEntry.profit), Decimal("0")))
        .select_from(LedgerEntry)
        .where(LedgerEntry.closed_at >= month_start)
    )

    # Funnel counts
    total_messages = await db.scalar(select(func.count()).select_from(RawMessage))
    total_orders = await db.scalar(select(func.count()).select_from(Order))
    total_deals = await db.scalar(select(func.count()).select_from(DetectedDeal))
    closed_deals = await db.scalar(
        select(func.count())
        .select_from(DetectedDeal)
        .where(DetectedDeal.status.in_([DealStatus.WON, DealStatus.LOST]))
    )

    return MetricsResponse(
        total_chats=chat_row.total,
        target_chats=target_chats,
        active_chats=chat_row.active,
        messages_today=msg_row.total,
        messages_filtered=msg_row.processed,
        filter_rate=round(filter_rate, 1),
        active_buy_orders=order_row.buy,
        active_sell_orders=order_row.sell,
        orders_today=order_row.today,
        deals_cold=deal_row.cold,
        deals_in_progress=deal_row.in_progress,
        deals_warm=deal_row.warm,
        deals_with_manager=deal_row.with_manager,
        deals_won=deal_row.won,
        deals_lost=deal_row.lost,
        profit_today=profit_today.scalar_one(),
        profit_week=profit_week.scalar_one(),
        profit_month=profit_month.scalar_one(),
        funnel_messages=total_messages or 0,
        funnel_orders=total_orders or 0,
        funnel_deals=total_deals or 0,
        funnel_closed=closed_deals or 0,
    )
