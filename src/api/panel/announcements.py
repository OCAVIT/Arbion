"""Panel announcements API endpoints for managers."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_manager
from src.db import get_db
from src.models import User
from src.models.announcement import Announcement, AnnouncementRead
from src.schemas.announcement import AnnouncementManagerResponse, UnreadCountResponse

router = APIRouter(prefix="/announcements")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def announcements_page(
    request: Request,
    current_user: User = Depends(require_manager),
):
    """Render announcements page for manager."""
    return templates.TemplateResponse(
        "panel/announcements.html",
        {"request": request, "user": current_user},
    )


@router.get("/list", response_model=list[AnnouncementManagerResponse])
async def list_announcements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Get all active announcements for manager (newest first)."""
    result = await db.execute(
        select(Announcement)
        .where(Announcement.is_active == True)
        .order_by(Announcement.created_at.desc())
    )
    announcements = result.scalars().all()

    # Get read status for current user
    read_result = await db.execute(
        select(AnnouncementRead.announcement_id).where(
            AnnouncementRead.user_id == current_user.id
        )
    )
    read_ids = set(read_result.scalars().all())

    items = []
    for a in announcements:
        items.append(
            AnnouncementManagerResponse(
                id=a.id,
                title=a.title,
                content=a.content,
                created_at=a.created_at,
                updated_at=a.updated_at,
                is_read=a.id in read_ids,
            )
        )
    return items


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Get count of unread announcements for badge/notification."""
    # All active announcements
    all_result = await db.execute(
        select(Announcement.id).where(Announcement.is_active == True)
    )
    all_ids = set(all_result.scalars().all())

    # Read by this user
    read_result = await db.execute(
        select(AnnouncementRead.announcement_id).where(
            AnnouncementRead.user_id == current_user.id
        )
    )
    read_ids = set(read_result.scalars().all())

    unread_count = len(all_ids - read_ids)
    return UnreadCountResponse(unread_count=unread_count)


@router.post("/{announcement_id}/mark-read")
async def mark_as_read(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Mark an announcement as read by current user."""
    # Check if already read
    existing = await db.execute(
        select(AnnouncementRead).where(
            AnnouncementRead.announcement_id == announcement_id,
            AnnouncementRead.user_id == current_user.id,
        )
    )
    if existing.scalar_one_or_none():
        return {"success": True, "already_read": True}

    read_record = AnnouncementRead(
        announcement_id=announcement_id,
        user_id=current_user.id,
    )
    db.add(read_record)
    await db.commit()

    return {"success": True, "already_read": False}


@router.post("/mark-all-read")
async def mark_all_as_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Mark all active announcements as read."""
    # Get all active announcement IDs
    all_result = await db.execute(
        select(Announcement.id).where(Announcement.is_active == True)
    )
    all_ids = set(all_result.scalars().all())

    # Get already read
    read_result = await db.execute(
        select(AnnouncementRead.announcement_id).where(
            AnnouncementRead.user_id == current_user.id
        )
    )
    read_ids = set(read_result.scalars().all())

    # Create read records for unread
    unread_ids = all_ids - read_ids
    for ann_id in unread_ids:
        db.add(AnnouncementRead(
            announcement_id=ann_id,
            user_id=current_user.id,
        ))

    if unread_ids:
        await db.commit()

    return {"success": True, "marked_count": len(unread_ids)}
