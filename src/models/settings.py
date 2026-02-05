"""
SystemSetting model for application configuration.
"""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class SystemSetting(Base):
    """
    Key-value store for system settings.

    Settings are stored as JSON values to support complex types.
    Default settings are created on application startup.

    Common keys:
    - target_chat_count: Target number of monitored chats
    - assignment_mode: "auto" or "free_pool"
    - max_deals_per_manager: Max concurrent deals per manager
    - min_margin_threshold: Minimum margin % to create a deal
    - parser_interval_minutes: Parser job interval
    - matcher_interval_minutes: Matcher job interval
    - negotiator_interval_minutes: Negotiator job interval
    - seed_queries: List of search queries for chat discovery
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )
    value: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="JSON value - use {'v': ...} wrapper for simple values",
    )

    def __repr__(self) -> str:
        return f"<SystemSetting(key='{self.key}')>"

    def get_value(self):
        """Get the actual value from the JSON wrapper."""
        if isinstance(self.value, dict) and "v" in self.value:
            return self.value["v"]
        return self.value

    def set_value(self, val):
        """Set value with JSON wrapper."""
        self.value = {"v": val}
