"""
Order model for buy/sell requests.
"""

from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Numeric, String, Text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class OrderType(str, Enum):
    """Type of order."""
    BUY = "buy"    # Someone wants to buy
    SELL = "sell"  # Someone wants to sell


class Order(Base, TimestampMixin):
    """
    Extracted order from Telegram message.

    Orders are extracted from raw_messages by the parser service.
    The matcher service then pairs buy and sell orders to create deals.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_type: Mapped[OrderType] = mapped_column(
        SQLAlchemyEnum(OrderType),
        nullable=False,
        index=True,
    )
    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
    )
    sender_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
    )
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    product: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    quantity: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    region: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    raw_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    contact_info: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, type={self.order_type}, product='{self.product}')>"
