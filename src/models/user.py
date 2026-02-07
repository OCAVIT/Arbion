"""
User model for authentication and role management.
"""

import secrets
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Numeric, String, Text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.audit import AuditLog
    from src.models.deal import DetectedDeal


class UserRole(str, Enum):
    """User roles for access control."""
    OWNER = "owner"
    MANAGER = "manager"


def generate_invite_token() -> str:
    """Generate a secure random invite token."""
    return secrets.token_urlsafe(32)


class User(Base, TimestampMixin):
    """
    User account model.

    - owner: Full access to all features, deals, and financial data
    - manager: Limited access to assigned deals only, no financial data
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        SQLAlchemyEnum(
            UserRole,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Commission rate for managers (fraction, e.g. 0.10 = 10%)
    commission_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        default=Decimal("0.10"),
        server_default="0.10",
        comment="Manager commission rate as fraction of margin",
    )

    # Unique invite token for manager login links
    invite_token: Mapped[Optional[str]] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True,
        default=generate_invite_token,
        comment="Unique token for manager's personal login link",
    )

    # Strategic update fields
    niches: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="JSON array of niches: [\"construction\", \"agriculture\"]",
    )
    level: Mapped[str] = mapped_column(
        String(20),
        default="junior",
        server_default="junior",
        nullable=False,
    )
    telegram_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )

    # Relationships
    assigned_deals: Mapped[List["DetectedDeal"]] = relationship(
        "DetectedDeal",
        back_populates="manager",
        foreign_keys="DetectedDeal.manager_id",
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="user",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role={self.role})>"
