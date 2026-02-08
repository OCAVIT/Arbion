"""
Database models for Arbion.

All models are exported here for convenient imports:
    from src.models import User, DetectedDeal, Order, etc.
"""

from src.models.announcement import Announcement, AnnouncementRead
from src.models.audit import AuditAction, AuditLog
from src.models.base import Base, BaseModel, TimestampMixin
from src.models.chat import ChatSource, ChatStatus, MonitoredChat
from src.models.deal import DealModel, DealStatus, DetectedDeal, LeadSource, PaymentStatus
from src.models.ledger import LedgerEntry
from src.models.negotiation import (
    MessageRole,
    MessageTarget,
    Negotiation,
    NegotiationMessage,
    NegotiationStage,
)
from src.models.order import Order, OrderType
from src.models.outbox import OutboxMessage, OutboxStatus
from src.models.raw_message import RawMessage
from src.models.settings import SystemSetting
from src.models.user import User, UserRole

__all__ = [
    # Announcement
    "Announcement",
    "AnnouncementRead",
    # Base
    "Base",
    "BaseModel",
    "TimestampMixin",
    # User
    "User",
    "UserRole",
    # Chat
    "MonitoredChat",
    "ChatStatus",
    "ChatSource",
    # Order
    "Order",
    "OrderType",
    # Deal
    "DetectedDeal",
    "DealStatus",
    "DealModel",
    "LeadSource",
    "PaymentStatus",
    # Negotiation
    "Negotiation",
    "NegotiationMessage",
    "NegotiationStage",
    "MessageRole",
    "MessageTarget",
    # Ledger
    "LedgerEntry",
    # Settings
    "SystemSetting",
    # Audit
    "AuditLog",
    "AuditAction",
    # Telegram
    "RawMessage",
    "OutboxMessage",
    "OutboxStatus",
]
