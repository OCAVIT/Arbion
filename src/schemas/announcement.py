"""Pydantic schemas for announcements."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None


class AnnouncementResponse(BaseModel):
    id: int
    title: str
    content: str
    is_active: bool
    created_by: int
    author_name: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AnnouncementManagerResponse(BaseModel):
    """Announcement as seen by manager, includes read status."""
    id: int
    title: str
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    is_read: bool = False

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    unread_count: int
