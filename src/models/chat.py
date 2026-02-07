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
    SEARCH = "search"          # Found via search
    MANUAL = "manual"          # Manually added
    INVITE = "invite"          # Joined via invite


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
    title: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    source: Mapped[ChatSource] = mapped_column(
        SQLAlchemyEnum(
            ChatSource,
            name="chatsource",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    status: Mapped[ChatStatus] = mapped_column(
        SQLAlchemyEnum(
            ChatStatus,
            name="chatstatus",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ChatStatus.PROBATION,
        nullable=True,
    )
    useful_ratio: Mapped[Optional[float]] = mapped_column(
        Float,
        default=0.0,
        nullable=True,
        comment="Percentage of messages that passed pre_filter",
    )
    orders_found: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=True,
    )
    deals_created: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=True,
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Strategic update fields
    niche: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    platform: Mapped[str] = mapped_column(
        String(20),
        default="telegram",
        server_default="telegram",
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<MonitoredChat(id={self.id}, title='{self.title}', status={self.status})>"
