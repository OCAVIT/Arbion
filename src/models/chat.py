"""
MonitoredChat model for tracking Telegram groups.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, Integer, String
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class ChatStatus(str, Enum):
    """Status of monitored chat."""
    ACTIVE = "active"          # Actively monitored
    PROBATION = "probation"    # New, being evaluated
    LEFT = "left"              # Bot left the chat
    BLACKLISTED = "blacklisted"  # Permanently blocked


class ChatSource(str, Enum):
    """How the chat was discovered."""
    SEED = "seed"              # Found via seed search query
    INVITE_LINK = "invite_link"  # Joined via invite link


class MonitoredChat(Base, TimestampMixin):
    """
    Telegram chat/group being monitored for orders.

    The system automatically discovers and joins chats based on
    seed queries. Chats start in 'probation' status and become
    'active' if they prove useful (high useful_ratio).
    """

    __tablename__ = "monitored_chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    member_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    status: Mapped[ChatStatus] = mapped_column(
        SQLAlchemyEnum(ChatStatus),
        default=ChatStatus.PROBATION,
        nullable=False,
    )
    useful_ratio: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Percentage of messages that passed pre_filter",
    )
    orders_found: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    deals_created: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    source: Mapped[ChatSource] = mapped_column(
        SQLAlchemyEnum(ChatSource),
        nullable=False,
    )
    last_checked: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<MonitoredChat(id={self.id}, title='{self.title}', status={self.status})>"
