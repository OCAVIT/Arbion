"""
DetectedDeal model for matched buy/sell pairs.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.negotiation import Negotiation
    from src.models.order import Order
    from src.models.user import User


class DealStatus(str, Enum):
    """Status of the deal in the pipeline."""
    COLD = "cold"                      # Just created, not contacted
    IN_PROGRESS = "in_progress"        # AI is negotiating
    WARM = "warm"                      # Ready for human manager
    HANDED_TO_MANAGER = "handed_to_manager"  # Assigned to manager
    WON = "won"                        # Successfully closed
    LOST = "lost"                      # Deal failed


class DetectedDeal(Base, TimestampMixin):
    """
    A matched deal between a buyer and seller.

    Created by the matcher service when compatible buy/sell orders
    are found. The negotiator AI then initiates contact with the seller.
    Once warm, the deal is handed to a human manager.

    SECURITY NOTE:
    - Managers should NEVER see: buy_price, margin, profit, buyer_*
    - Only the owner has access to financial details
    """

    __tablename__ = "detected_deals"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Order references
    buy_order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
    )
    sell_order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
    )

    # Product info
    product: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    region: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    # Financial data (OWNER ONLY)
    buy_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    sell_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    margin: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    profit: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Actual profit after deal closes",
    )

    # Status
    status: Mapped[DealStatus] = mapped_column(
        SQLAlchemyEnum(
            DealStatus,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=DealStatus.COLD,
        nullable=False,
        index=True,
    )

    # Manager assignment
    manager_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # AI insights
    ai_insight: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="AI-generated summary of the deal",
    )
    ai_resolution: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="AI explanation of deal outcome",
    )

    # Deal details (gathered during negotiation)
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Owner/manager notes about the deal",
    )
    target_sell_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Target resale price set by owner",
    )
    seller_condition: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Product condition reported by seller",
    )
    seller_city: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Seller city extracted from negotiation",
    )
    seller_specs: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Product specs from seller (config, memory, etc.)",
    )
    seller_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Seller phone number",
    )
    buyer_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Buyer phone number",
    )
    buyer_preferences: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Buyer preferences (color, size, config, etc.)",
    )

    # Buyer info (OWNER ONLY - never expose to managers)
    buyer_chat_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )
    buyer_sender_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )

    # Relationships
    buy_order: Mapped["Order"] = relationship(
        "Order",
        foreign_keys=[buy_order_id],
    )
    sell_order: Mapped["Order"] = relationship(
        "Order",
        foreign_keys=[sell_order_id],
    )
    manager: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="assigned_deals",
    )
    negotiation: Mapped[Optional["Negotiation"]] = relationship(
        "Negotiation",
        back_populates="deal",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<DetectedDeal(id={self.id}, product='{self.product}', status={self.status})>"
