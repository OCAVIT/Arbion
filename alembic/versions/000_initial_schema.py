"""Initial database schema

Revision ID: 000_initial_schema
Revises:
Create Date: 2026-02-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "000_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all initial tables."""

    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("role", sa.Enum("owner", "manager", name="userrole"), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("invite_token", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_invite_token", "users", ["invite_token"], unique=True)

    # Monitored chats table
    op.create_table(
        "monitored_chats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("source", sa.Enum("search", "manual", "invite", name="chatsource"), nullable=False),
        sa.Column("status", sa.Enum("probation", "active", "left", "blacklisted", name="chatstatus"), default="probation"),
        sa.Column("useful_ratio", sa.Numeric(5, 2), default=0),
        sa.Column("orders_found", sa.Integer(), default=0),
        sa.Column("deals_created", sa.Integer(), default=0),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_monitored_chats_chat_id", "monitored_chats", ["chat_id"], unique=True)
    op.create_index("ix_monitored_chats_status", "monitored_chats", ["status"])

    # Orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_type", sa.Enum("buy", "sell", name="ordertype"), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("sender_id", sa.BigInteger(), nullable=True),
        sa.Column("product", sa.String(255), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("quantity", sa.String(100), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("contact_info", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("is_matched", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_orders_order_type", "orders", ["order_type"])
    op.create_index("ix_orders_product", "orders", ["product"])
    op.create_index("ix_orders_is_matched", "orders", ["is_matched"])

    # Detected deals table
    op.create_table(
        "detected_deals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("buy_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("sell_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("product", sa.String(255), nullable=False),
        sa.Column("buy_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("sell_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("margin", sa.Numeric(12, 2), nullable=False),
        sa.Column("profit", sa.Numeric(12, 2), nullable=True),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("status", sa.Enum("cold", "in_progress", "warm", "handed_to_manager", "won", "lost", name="dealstatus"), default="cold"),
        sa.Column("manager_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_insight", sa.Text(), nullable=True),
        sa.Column("ai_resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_detected_deals_status", "detected_deals", ["status"])
    op.create_index("ix_detected_deals_manager_id", "detected_deals", ["manager_id"])

    # Negotiations table
    op.create_table(
        "negotiations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("detected_deals.id"), unique=True, nullable=False),
        sa.Column("stage", sa.Enum("initial", "contacted", "negotiating", "agreed", "closed", name="negotiationstage"), default="initial"),
        sa.Column("seller_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("seller_sender_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Negotiation messages table
    op.create_table(
        "negotiation_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("negotiation_id", sa.Integer(), sa.ForeignKey("negotiations.id"), nullable=False),
        sa.Column("role", sa.Enum("ai", "seller", "manager", "system", name="messagerole"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sent_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_negotiation_messages_negotiation_id", "negotiation_messages", ["negotiation_id"])

    # Ledger table (financial records)
    op.create_table(
        "ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deal_id", sa.Integer(), sa.ForeignKey("detected_deals.id"), nullable=False),
        sa.Column("buy_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("sell_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("profit", sa.Numeric(12, 2), nullable=False),
        sa.Column("closed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_ledger_deal_id", "ledger", ["deal_id"])

    # Audit logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.Enum(
            "login", "logout", "view_deal", "send_message", "take_deal",
            "close_deal", "update_deal", "create_manager", "update_manager",
            "delete_manager", "update_settings", "leave_chat", "blacklist_chat",
            name="auditaction"
        ), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("action_metadata", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # System settings table
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Raw messages table (Telegram messages)
    op.create_table(
        "raw_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("processed", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_raw_messages_chat_id", "raw_messages", ["chat_id"])
    op.create_index("ix_raw_messages_processed", "raw_messages", ["processed"])
    op.create_unique_constraint("uq_raw_messages_chat_message", "raw_messages", ["chat_id", "message_id"])

    # Outbox messages table (message queue)
    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipient_id", sa.BigInteger(), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("pending", "sent", "failed", name="outboxstatus"), default="pending"),
        sa.Column("negotiation_id", sa.Integer(), sa.ForeignKey("negotiations.id"), nullable=True),
        sa.Column("sent_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_outbox_messages_status", "outbox_messages", ["status"])


def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_table("outbox_messages")
    op.drop_table("raw_messages")
    op.drop_table("system_settings")
    op.drop_table("audit_logs")
    op.drop_table("ledger")
    op.drop_table("negotiation_messages")
    op.drop_table("negotiations")
    op.drop_table("detected_deals")
    op.drop_table("orders")
    op.drop_table("monitored_chats")
    op.drop_table("users")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS outboxstatus")
    op.execute("DROP TYPE IF EXISTS auditaction")
    op.execute("DROP TYPE IF EXISTS messagerole")
    op.execute("DROP TYPE IF EXISTS negotiationstage")
    op.execute("DROP TYPE IF EXISTS dealstatus")
    op.execute("DROP TYPE IF EXISTS ordertype")
    op.execute("DROP TYPE IF EXISTS chatstatus")
    op.execute("DROP TYPE IF EXISTS chatsource")
    op.execute("DROP TYPE IF EXISTS userrole")
