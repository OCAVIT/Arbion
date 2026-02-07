"""
Negotiation model for tracking conversations with sellers.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.deal import DetectedDeal
    from src.models.user import User


class NegotiationStage(str, Enum):
    """Stage of the negotiation process."""
    INITIAL = "initial"              # First contact
    CONTACTED = "contacted"          # Seller responded
    NEGOTIATING = "negotiating"      # Actively discussing
    PRICE_DISCUSSION = "price_discussion"  # Discussing price/terms
    LOGISTICS = "logistics"          # Discussing delivery
    WARM = "warm"                    # Ready for human
    HANDED_TO_MANAGER = "handed_to_manager"  # Manager took over
    CLOSED = "closed"                # Negotiation ended


class MessageRole(str, Enum):
    """Who sent the message."""
    AI = "ai"           # AI negotiator
    SELLER = "seller"   # The seller
    BUYER = "buyer"     # The buyer
    MANAGER = "manager"  # Human manager


class MessageTarget(str, Enum):
    """Who the message is directed to (which chat)."""
    SELLER = "seller"   # Chat with the seller
    BUYER = "buyer"     # Chat with the buyer


class Negotiation(Base, TimestampMixin):
    """
    Tracks the negotiation process for a deal.

    Each deal has one negotiation containing all messages
    exchanged with the seller.
    """

    __tablename__ = "negotiations"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[int] = mapped_column(
        ForeignKey("detected_deals.id"),
        unique=True,
        nullable=False,
    )
    stage: Mapped[NegotiationStage] = mapped_column(
        SQLAlchemyEnum(
            NegotiationStage,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=NegotiationStage.INITIAL,
        nullable=False,
    )

    # Seller contact info (sensitive - mask for managers)
    seller_chat_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    seller_sender_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # Relationships
    deal: Mapped["DetectedDeal"] = relationship(
        "DetectedDeal",
        back_populates="negotiation",
    )
    messages: Mapped[List["NegotiationMessage"]] = relationship(
        "NegotiationMessage",
        back_populates="negotiation",
        order_by="NegotiationMessage.created_at",
    )

    def __repr__(self) -> str:
        return f"<Negotiation(id={self.id}, deal_id={self.deal_id}, stage={self.stage})>"


class NegotiationMessage(Base):
    """
    Individual message in a negotiation.

    SECURITY NOTE:
    - Phone numbers and usernames in content should be masked for managers
    - The mask_sensitive() utility handles this at serialization time
    """

    __tablename__ = "negotiation_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    negotiation_id: Mapped[int] = mapped_column(
        ForeignKey("negotiations.id"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        SQLAlchemyEnum(
            MessageRole,
            name="messagerole",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    target: Mapped[MessageTarget] = mapped_column(
        SQLAlchemyEnum(
            MessageTarget,
            name="messagetarget",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=MessageTarget.SELLER,
        nullable=False,
        comment="Which chat this message belongs to (seller or buyer)",
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    telegram_message_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram message ID for reply tracking",
    )
    reply_to_message_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Telegram message ID this is replying to",
    )
    sent_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        comment="User ID if sent by manager",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    negotiation: Mapped["Negotiation"] = relationship(
        "Negotiation",
        back_populates="messages",
    )
    sent_by: Mapped[Optional["User"]] = relationship("User")

    def __repr__(self) -> str:
        return f"<NegotiationMessage(id={self.id}, role='{self.role}')>"
