"""
Ledger model for financial tracking.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.deal import DetectedDeal
    from src.models.user import User


class LedgerEntry(Base, TimestampMixin):
    """
    Financial ledger entry for closed deals.

    SECURITY NOTE:
    - This table is OWNER ONLY
    - Managers should NEVER have access to this data
    - Contains actual profit/loss information
    """

    __tablename__ = "ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(
        ForeignKey("detected_deals.id"),
        nullable=False,
        index=True,
    )
    buy_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    sell_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    profit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    closed_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    deal: Mapped["DetectedDeal"] = relationship("DetectedDeal")
    closed_by: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<LedgerEntry(id={self.id}, deal_id={self.deal_id}, profit={self.profit})>"
