"""Admin chat management API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_owner
from src.db import get_db
from src.models import AuditAction, ChatStatus, MonitoredChat, SystemSetting, User
from src.schemas.chat import (
    ChatListResponse,
    ChatResponse,
    ChatStatsResponse,
    SeedQueryCreate,
)
from src.utils.audit import get_client_ip, log_action

router = APIRouter(prefix="/chats")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def chats_page(
    request: Request,
    current_user: User = Depends(require_owner),
):
    """Render chats management page."""
    return templates.TemplateResponse(
        "admin/chats.html",
        {"request": request, "user": current_user},
    )


@router.get("/list", response_model=ChatListResponse)
async def list_chats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    sort_by: str = Query("useful_ratio", regex="^(useful_ratio|orders_found|deals_created|created_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List all monitored chats with filters."""
    query = select(MonitoredChat)

    # Apply status filter
    if status_filter:
        query = query.where(MonitoredChat.status == status_filter)

    # Apply search
    if search:
        query = query.where(MonitoredChat.title.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # Apply sorting
    sort_column = getattr(MonitoredChat, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    chats = result.scalars().all()

    return ChatListResponse(
        items=[ChatResponse.model_validate(c) for c in chats],
        total=total or 0,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page if total else 0,
    )


@router.get("/stats", response_model=ChatStatsResponse)
async def get_chat_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Get chat statistics."""
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(MonitoredChat.status == ChatStatus.ACTIVE).label("active"),
            func.count().filter(MonitoredChat.status == ChatStatus.PROBATION).label("probation"),
            func.count().filter(MonitoredChat.status == ChatStatus.LEFT).label("left"),
            func.count().filter(MonitoredChat.status == ChatStatus.BLACKLISTED).label("blacklisted"),
        ).select_from(MonitoredChat)
    )
    row = result.one()

    # Get target
    target_setting = await db.get(SystemSetting, "target_chat_count")
    target = target_setting.get_value() if target_setting else 100

    return ChatStatsResponse(
        total_chats=row.total,
        active_chats=row.active,
        probation_chats=row.probation,
        left_chats=row.left,
        blacklisted_chats=row.blacklisted,
        target_chat_count=target,
    )


@router.post("/target")
async def set_target_chat_count(
    target: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Set target number of chats to monitor."""
    if target < 0 or target > 10000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target must be between 0 and 10000",
        )

    setting = await db.get(SystemSetting, "target_chat_count")
    if setting:
        setting.set_value(target)
    else:
        setting = SystemSetting(key="target_chat_count", value={"v": target})
        db.add(setting)

    await db.commit()
    return {"success": True, "target_chat_count": target}


@router.post("/seeds")
async def add_seed_query(
    request: Request,
    data: SeedQueryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Add a new seed search query for chat discovery."""
    setting = await db.get(SystemSetting, "seed_queries")
    queries = setting.get_value() if setting else []

    if data.query in queries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query already exists",
        )

    queries.append(data.query)

    if setting:
        setting.set_value(queries)
    else:
        setting = SystemSetting(key="seed_queries", value={"v": queries})
        db.add(setting)

    await db.commit()
    return {"success": True, "queries": queries}


@router.delete("/seeds/{query}")
async def remove_seed_query(
    query: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Remove a seed search query."""
    setting = await db.get(SystemSetting, "seed_queries")
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No seed queries configured",
        )

    queries = setting.get_value()
    if query not in queries:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Query not found",
        )

    queries.remove(query)
    setting.set_value(queries)
    await db.commit()

    return {"success": True, "queries": queries}


@router.post("/{chat_id}/leave")
async def leave_chat(
    request: Request,
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Mark chat as left (stop monitoring)."""
    chat = await db.execute(
        select(MonitoredChat).where(MonitoredChat.id == chat_id)
    )
    chat = chat.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )

    chat.status = ChatStatus.LEFT

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.LEAVE_CHAT,
        target_type="chat",
        target_id=chat_id,
        action_metadata={"title": chat.title},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True}


@router.post("/{chat_id}/blacklist")
async def blacklist_chat(
    request: Request,
    chat_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Permanently blacklist a chat."""
    chat = await db.execute(
        select(MonitoredChat).where(MonitoredChat.id == chat_id)
    )
    chat = chat.scalar_one_or_none()

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat not found",
        )

    chat.status = ChatStatus.BLACKLISTED

    await log_action(
        db=db,
        user_id=current_user.id,
        action=AuditAction.BLACKLIST_CHAT,
        target_type="chat",
        target_id=chat_id,
        action_metadata={"title": chat.title},
        ip_address=get_client_ip(request),
    )

    await db.commit()
    return {"success": True}
