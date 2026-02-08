"""Admin announcements API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import require_owner
from src.db import get_db
from src.models import User
from src.models.announcement import Announcement
from src.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementResponse,
    AnnouncementUpdate,
)

router = APIRouter(prefix="/announcements")
templates = Jinja2Templates(directory="src/templates")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def announcements_page(
    request: Request,
    current_user: User = Depends(require_owner),
):
    """Render announcements management page."""
    return templates.TemplateResponse(
        "admin/announcements.html",
        {"request": request, "user": current_user},
    )


@router.get("/list", response_model=list[AnnouncementResponse])
async def list_announcements(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Get all announcements (newest first)."""
    result = await db.execute(
        select(Announcement)
        .order_by(Announcement.created_at.desc())
    )
    announcements = result.scalars().all()

    items = []
    for a in announcements:
        author = await db.get(User, a.created_by)
        items.append(
            AnnouncementResponse(
                id=a.id,
                title=a.title,
                content=a.content,
                is_active=a.is_active,
                created_by=a.created_by,
                author_name=author.display_name if author else "Unknown",
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
        )
    return items


@router.post("/create", response_model=AnnouncementResponse)
async def create_announcement(
    data: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Create a new announcement."""
    announcement = Announcement(
        title=data.title,
        content=data.content,
        created_by=current_user.id,
    )
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)

    return AnnouncementResponse(
        id=announcement.id,
        title=announcement.title,
        content=announcement.content,
        is_active=announcement.is_active,
        created_by=announcement.created_by,
        author_name=current_user.display_name,
        created_at=announcement.created_at,
        updated_at=announcement.updated_at,
    )


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    announcement_id: int,
    data: AnnouncementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Update an existing announcement."""
    announcement = await db.get(Announcement, announcement_id)
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объявление не найдено",
        )

    if data.title is not None:
        announcement.title = data.title
    if data.content is not None:
        announcement.content = data.content
    if data.is_active is not None:
        announcement.is_active = data.is_active

    # Update timestamp manually since we use onupdate
    announcement.updated_at = sa_func.now()

    await db.commit()
    await db.refresh(announcement)

    author = await db.get(User, announcement.created_by)
    return AnnouncementResponse(
        id=announcement.id,
        title=announcement.title,
        content=announcement.content,
        is_active=announcement.is_active,
        created_by=announcement.created_by,
        author_name=author.display_name if author else "Unknown",
        created_at=announcement.created_at,
        updated_at=announcement.updated_at,
    )


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    """Delete an announcement."""
    announcement = await db.get(Announcement, announcement_id)
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Объявление не найдено",
        )

    await db.delete(announcement)
    await db.commit()

    return {"success": True}
