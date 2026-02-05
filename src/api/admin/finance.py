"""Admin finance API endpoints."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.dependencies import require_owner
from src.db import get_db
from src.models import DetectedDeal, LedgerEntry, User
from src.schemas.dashboard import LedgerEntryResponse, LedgerSummaryResponse

router = APIRouter(prefix="/finance")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def finance_page(
    request: Request,
    current_user: User = Depends(require_owner),
):
    """Render finance page."""
    return templates.TemplateResponse(
        "admin/finance.html",
        {"request": request, "user": current_user},
    )


@router.get("/ledger")
async def get_ledger(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Get ledger entries."""
    query = (
        select(LedgerEntry)
        .options(
            selectinload(LedgerEntry.deal),
            selectinload(LedgerEntry.closed_by),
        )
    )

    if start_date:
        query = query.where(LedgerEntry.closed_at >= start_date)

    if end_date:
        query = query.where(LedgerEntry.closed_at <= end_date)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Apply sorting and pagination
    query = query.order_by(LedgerEntry.closed_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    entries = result.scalars().all()

    return {
        "items": [
            LedgerEntryResponse(
                id=entry.id,
                deal_id=entry.deal_id,
                product=entry.deal.product if entry.deal else "Unknown",
                buy_amount=entry.buy_amount,
                sell_amount=entry.sell_amount,
                profit=entry.profit,
                closed_by=entry.closed_by.display_name if entry.closed_by else "System",
                closed_at=entry.closed_at,
            )
            for entry in entries
        ],
        "total": total or 0,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


@router.get("/summary", response_model=LedgerSummaryResponse)
async def get_finance_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Get financial summary."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start.replace(day=1)

    # Total profit and deals
    totals = await db.execute(
        select(
            func.coalesce(func.sum(LedgerEntry.profit), Decimal("0")).label("total_profit"),
            func.count().label("total_deals"),
        ).select_from(LedgerEntry)
    )
    total_row = totals.one()

    avg_profit = (
        total_row.total_profit / total_row.total_deals
        if total_row.total_deals > 0
        else Decimal("0")
    )

    # Profit by period
    profit_today = await db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.profit), Decimal("0")))
        .select_from(LedgerEntry)
        .where(LedgerEntry.closed_at >= today_start)
    )

    profit_week = await db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.profit), Decimal("0")))
        .select_from(LedgerEntry)
        .where(LedgerEntry.closed_at >= week_start)
    )

    profit_month = await db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.profit), Decimal("0")))
        .select_from(LedgerEntry)
        .where(LedgerEntry.closed_at >= month_start)
    )

    return LedgerSummaryResponse(
        total_profit=total_row.total_profit,
        total_deals=total_row.total_deals,
        avg_profit_per_deal=avg_profit,
        profit_by_period={
            "today": profit_today,
            "week": profit_week,
            "month": profit_month,
        },
    )
