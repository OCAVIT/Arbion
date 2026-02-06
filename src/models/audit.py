"""
AuditLog model for tracking user actions.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.user import User


class AuditAction(str, Enum):
    """Types of auditable actions."""
    LOGIN = "login"
    LOGOUT = "logout"
    VIEW_DEAL = "view_deal"
    SEND_MESSAGE = "send_message"
    TAKE_DEAL = "take_deal"
    CLOSE_DEAL = "close_deal"
    DELETE_DEAL = "delete_deal"
    UPDATE_DEAL = "update_deal"
    CREATE_MANAGER = "create_manager"
    UPDATE_MANAGER = "update_manager"
    DELETE_MANAGER = "delete_manager"
    UPDATE_SETTINGS = "update_settings"
    LEAVE_CHAT = "leave_chat"
    BLACKLIST_CHAT = "blacklist_chat"


class AuditLog(Base):
    """
    Audit log for tracking all user actions.

    This is critical for security - every action by managers
    is logged here for owner review.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    action: Mapped[AuditAction] = mapped_column(
        SQLAlchemyEnum(
            AuditAction,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    target_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Type of entity affected (deal, manager, chat, etc)",
    )
    target_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="ID of the affected entity",
    )
    action_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional context about the action",
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        comment="IPv4 or IPv6 address",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="audit_logs",
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, user_id={self.user_id}, action={self.action})>"
