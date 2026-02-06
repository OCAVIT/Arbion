"""Admin orders API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_owner
from src.db import get_db
from src.models import DetectedDeal, MonitoredChat, Order, OrderType, User
from src.schemas.order import OrderListResponse, OrderResponse, OrderStatsResponse

router = APIRouter(prefix="/orders")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def orders_page(
    request: Request,
    current_user: User = Depends(require_owner),
):
    """Render orders page."""
    return templates.TemplateResponse(
        "admin/orders.html",
        {"request": request, "user": current_user},
    )


@router.get("/list", response_model=OrderListResponse)
async def list_orders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
    order_type: Optional[str] = Query(None, alias="type"),
    product: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    active_only: bool = Query(True),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List all orders with filters."""
    query = select(Order)

    # Apply filters
    if order_type:
        query = query.where(Order.order_type == order_type)

    if product:
        query = query.where(Order.product.ilike(f"%{product}%"))

    if region:
        query = query.where(Order.region.ilike(f"%{region}%"))

    if active_only:
        query = query.where(Order.is_active == True)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Apply sorting and pagination
    query = query.order_by(Order.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    orders = result.scalars().all()

    # Get chat titles
    chat_ids = {o.chat_id for o in orders}
    if chat_ids:
        chats_result = await db.execute(
            select(MonitoredChat.chat_id, MonitoredChat.title)
            .where(MonitoredChat.chat_id.in_(chat_ids))
        )
        chat_titles = {row.chat_id: row.title for row in chats_result}
    else:
        chat_titles = {}

    # Build response
    items = []
    for order in orders:
        resp = OrderResponse.model_validate(order)
        # Используем chat_title из MonitoredChat, или contact_info для личных чатов
        resp.chat_title = chat_titles.get(order.chat_id) or order.contact_info or f"ID: {order.sender_id}"
        items.append(resp)

    return OrderListResponse(
        items=items,
        total=total or 0,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page if total else 0,
    )


@router.get("/stats", response_model=OrderStatsResponse)
async def get_order_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Get order statistics."""
    from datetime import datetime, timezone

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Order.order_type == OrderType.BUY).label("buy"),
            func.count().filter(Order.order_type == OrderType.SELL).label("sell"),
            func.count().filter(Order.is_active == True).label("active"),
            func.count().filter(Order.created_at >= today_start).label("today"),
        ).select_from(Order)
    )
    row = result.one()

    return OrderStatsResponse(
        total_orders=row.total,
        buy_orders=row.buy,
        sell_orders=row.sell,
        active_orders=row.active,
        orders_today=row.today,
    )


@router.delete("/{order_id}")
async def delete_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Hard-delete an order. Fails if order is linked to a deal."""
    order = await db.get(Order, order_id)

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    # Проверяем, не привязана ли заявка к сделке
    linked_deal = await db.execute(
        select(DetectedDeal.id).where(
            (DetectedDeal.buy_order_id == order_id)
            | (DetectedDeal.sell_order_id == order_id)
        ).limit(1)
    )
    deal_id = linked_deal.scalar_one_or_none()
    if deal_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Заявка привязана к сделке #{deal_id}. Сначала удалите сделку.",
        )

    await db.delete(order)
    await db.commit()

    return {"success": True}
