"""System settings schemas."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    """Current system settings."""

    target_chat_count: int = Field(default=100)
    assignment_mode: str = Field(default="free_pool")  # "auto" or "free_pool"
    max_deals_per_manager: int = Field(default=15)
    min_margin_threshold: float = Field(default=5.0)
    parser_interval_minutes: int = Field(default=5)
    matcher_interval_minutes: int = Field(default=10)
    negotiator_interval_minutes: int = Field(default=15)
    seed_queries: List[str] = Field(default_factory=list)
    messaging_mode: str = Field(default="personal")  # "personal" or "business_account"


class SettingsUpdate(BaseModel):
    """Update system settings."""

    target_chat_count: Optional[int] = Field(None, ge=0, le=10000)
    assignment_mode: Optional[str] = Field(None, pattern="^(auto|free_pool)$")
    max_deals_per_manager: Optional[int] = Field(None, ge=1, le=100)
    min_margin_threshold: Optional[float] = Field(None, ge=0, le=100)
    parser_interval_minutes: Optional[int] = Field(None, ge=1, le=60)
    matcher_interval_minutes: Optional[int] = Field(None, ge=1, le=60)
    negotiator_interval_minutes: Optional[int] = Field(None, ge=1, le=60)
    messaging_mode: Optional[str] = Field(None, pattern="^(personal|business_account)$")


class SettingValue(BaseModel):
    """Single setting key-value pair."""

    key: str
    value: Any


class BulkSettingsUpdate(BaseModel):
    """Bulk update multiple settings."""

    settings: Dict[str, Any]
