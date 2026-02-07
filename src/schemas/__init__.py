"""Pydantic schemas for request/response validation."""

from src.schemas.auth import LoginRequest, LoginResponse, TokenPayload
from src.schemas.chat import (
    ChatCreate,
    ChatResponse,
    ChatUpdate,
    SeedQueryCreate,
    SeedQueryResponse,
)
from src.schemas.deal import (
    DealAssignRequest,
    DealCloseRequest,
    ManagerDealResponse,
    MessageResponse,
    OwnerDealResponse,
    SendMessageRequest,
)
from src.schemas.copilot import LeadCardResponse, SuggestedResponses
from src.schemas.order import OrderCreate, OrderResponse, OrderUpdate
from src.schemas.settings import SettingsResponse, SettingsUpdate
from src.schemas.user import (
    ManagerCreate,
    ManagerResponse,
    ManagerStatsResponse,
    ManagerUpdate,
    PasswordChange,
    ProfileResponse,
)

__all__ = [
    # Auth
    "LoginRequest",
    "LoginResponse",
    "TokenPayload",
    # User
    "ManagerCreate",
    "ManagerResponse",
    "ManagerUpdate",
    "ManagerStatsResponse",
    "ProfileResponse",
    "PasswordChange",
    # Deal
    "OwnerDealResponse",
    "ManagerDealResponse",
    "DealAssignRequest",
    "DealCloseRequest",
    "SendMessageRequest",
    "MessageResponse",
    # Chat
    "ChatCreate",
    "ChatResponse",
    "ChatUpdate",
    "SeedQueryCreate",
    "SeedQueryResponse",
    # Order
    "OrderCreate",
    "OrderResponse",
    "OrderUpdate",
    # Copilot
    "LeadCardResponse",
    "SuggestedResponses",
    # Settings
    "SettingsResponse",
    "SettingsUpdate",
]
