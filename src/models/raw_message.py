"""
RawMessage model for Telegram messages.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class RawMessage(Base):
    """
    Raw message from Telegram before processing.

    Messages are collected by the Telethon listener and stored here.
    The parser service then processes them to extract orders.
    """

    __tablename__ = "raw_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
    )
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    sender_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )
    chat_title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    raw_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    file_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="URL to uploaded media file",
    )
    processed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "message_id", name="uq_chat_message"),
    )

    def __repr__(self) -> str:
        return f"<RawMessage(id={self.id}, chat_id={self.chat_id}, message_id={self.message_id})>"
