"""Chat and seed query schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.chat import ChatSource, ChatStatus


class ChatCreate(BaseModel):
    """Manually add a chat to monitor."""

    chat_id: int
    title: str = Field(..., max_length=255)
    source: ChatSource = ChatSource.MANUAL


class ChatUpdate(BaseModel):
    """Update chat status."""

    status: Optional[ChatStatus] = None


class ChatResponse(BaseModel):
    """Chat information for admin view."""

    id: int
    chat_id: int
    title: Optional[str] = None
    username: Optional[str] = None
    status: Optional[ChatStatus] = None
    useful_ratio: Optional[float] = 0.0
    orders_found: int = 0
    deals_created: int = 0
    source: ChatSource
    last_message_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatListResponse(BaseModel):
    """Paginated list of chats."""

    items: List[ChatResponse]
    total: int
    page: int
    per_page: int
    pages: int


class ChatStatsResponse(BaseModel):
    """Chat statistics overview."""

    total_chats: int
    active_chats: int
    probation_chats: int
    left_chats: int
    blacklisted_chats: int
    target_chat_count: int


class SeedQueryCreate(BaseModel):
    """Add a new seed search query."""

    query: str = Field(..., min_length=2, max_length=200)


class SeedQueryResponse(BaseModel):
    """Seed query information."""

    id: int
    query: str
    created_at: datetime
    chats_found: int = 0


class DiscoveryLogEntry(BaseModel):
    """Log entry from chat discovery."""

    timestamp: datetime
    action: str
    details: str
    success: bool
