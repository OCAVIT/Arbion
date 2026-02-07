"""
OutboxMessage model for outgoing Telegram messages.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class OutboxStatus(str, Enum):
    """Status of outgoing message."""
    PENDING = "pending"  # Waiting to be sent
    SENT = "sent"        # Successfully sent
    FAILED = "failed"    # Failed to send


class OutboxMessage(Base):
    """
    Outgoing message queue for Telegram.

    Messages are added here by the API (manager/AI) and sent
    by the outbox_worker background task.
    """

    __tablename__ = "outbox_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
        comment="Telegram user/chat ID to send to",
    )
    message_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[OutboxStatus] = mapped_column(
        SQLAlchemyEnum(
            OutboxStatus,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=OutboxStatus.PENDING,
        nullable=False,
        index=True,
    )
    negotiation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("negotiations.id"),
        nullable=True,
        comment="Related negotiation if applicable",
    )
    sent_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        comment="User who initiated the message",
    )
    media_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Media type: photo, document",
    )
    media_file_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Temp file path for outgoing media",
    )
    file_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Original filename for documents",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error details if send failed",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<OutboxMessage(id={self.id}, status={self.status})>"
