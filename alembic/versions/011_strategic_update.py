"""Strategic update: add platform, niche, volume, lead_source, deal_model,
payment statuses, AI draft, market context, manager niches/level/telegram_id.

Revision ID: 011_strategic_update
Revises: 010_telegram_message_id
Create Date: 2026-02-07

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "011_strategic_update"
down_revision: Union[str, None] = "010_telegram_message_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(table: str, column: str) -> bool:
    """Check if a column already exists (idempotency guard)."""
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade() -> None:
    # ── orders ──────────────────────────────────────────────
    if not _col_exists("orders", "platform"):
        op.add_column(
            "orders",
            sa.Column("platform", sa.String(20), server_default="telegram", nullable=False),
        )
    if not _col_exists("orders", "niche"):
        op.add_column(
            "orders",
            sa.Column("niche", sa.String(50), nullable=True),
        )
    if not _col_exists("orders", "unit"):
        op.add_column(
            "orders",
            sa.Column("unit", sa.String(30), nullable=True),
        )
    if not _col_exists("orders", "volume_numeric"):
        op.add_column(
            "orders",
            sa.Column("volume_numeric", sa.Numeric(12, 2), nullable=True),
        )

    # ── detected_deals ──────────────────────────────────────
    if not _col_exists("detected_deals", "lead_source"):
        op.add_column(
            "detected_deals",
            sa.Column("lead_source", sa.String(20), server_default="system", nullable=False),
        )
    if not _col_exists("detected_deals", "niche"):
        op.add_column(
            "detected_deals",
            sa.Column("niche", sa.String(50), nullable=True),
        )
    if not _col_exists("detected_deals", "deal_model"):
        op.add_column(
            "detected_deals",
            sa.Column("deal_model", sa.String(20), server_default="agency", nullable=False),
        )
    if not _col_exists("detected_deals", "manager_commission_rate"):
        op.add_column(
            "detected_deals",
            sa.Column("manager_commission_rate", sa.Numeric(5, 4), nullable=True),
        )
    if not _col_exists("detected_deals", "buyer_payment_status"):
        op.add_column(
            "detected_deals",
            sa.Column("buyer_payment_status", sa.String(20), server_default="pending", nullable=False),
        )
    if not _col_exists("detected_deals", "seller_payment_status"):
        op.add_column(
            "detected_deals",
            sa.Column("seller_payment_status", sa.String(20), server_default="pending", nullable=False),
        )
    if not _col_exists("detected_deals", "our_commission_status"):
        op.add_column(
            "detected_deals",
            sa.Column("our_commission_status", sa.String(20), server_default="pending", nullable=False),
        )
    if not _col_exists("detected_deals", "payment_method"):
        op.add_column(
            "detected_deals",
            sa.Column("payment_method", sa.String(20), nullable=True),
        )
    if not _col_exists("detected_deals", "ai_draft_message"):
        op.add_column(
            "detected_deals",
            sa.Column("ai_draft_message", sa.Text(), nullable=True),
        )
    if not _col_exists("detected_deals", "market_price_context"):
        op.add_column(
            "detected_deals",
            sa.Column("market_price_context", sa.Text(), nullable=True),
        )
    if not _col_exists("detected_deals", "platform"):
        op.add_column(
            "detected_deals",
            sa.Column("platform", sa.String(20), server_default="telegram", nullable=False),
        )

    # ── users ───────────────────────────────────────────────
    if not _col_exists("users", "niches"):
        op.add_column(
            "users",
            sa.Column("niches", sa.Text(), nullable=True),
        )
    if not _col_exists("users", "level"):
        op.add_column(
            "users",
            sa.Column("level", sa.String(20), server_default="junior", nullable=False),
        )
    if not _col_exists("users", "telegram_user_id"):
        op.add_column(
            "users",
            sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        )

    # ── ledger ──────────────────────────────────────────────
    if not _col_exists("ledger", "deal_model"):
        op.add_column(
            "ledger",
            sa.Column("deal_model", sa.String(20), nullable=True),
        )
    if not _col_exists("ledger", "commission_rate_applied"):
        op.add_column(
            "ledger",
            sa.Column("commission_rate_applied", sa.Numeric(5, 4), nullable=True),
        )
    if not _col_exists("ledger", "lead_source"):
        op.add_column(
            "ledger",
            sa.Column("lead_source", sa.String(20), nullable=True),
        )

    # ── monitored_chats ─────────────────────────────────────
    if not _col_exists("monitored_chats", "niche"):
        op.add_column(
            "monitored_chats",
            sa.Column("niche", sa.String(50), nullable=True),
        )
    if not _col_exists("monitored_chats", "platform"):
        op.add_column(
            "monitored_chats",
            sa.Column("platform", sa.String(20), server_default="telegram", nullable=False),
        )


def downgrade() -> None:
    # ── monitored_chats (reverse) ───────────────────────────
    if _col_exists("monitored_chats", "platform"):
        op.drop_column("monitored_chats", "platform")
    if _col_exists("monitored_chats", "niche"):
        op.drop_column("monitored_chats", "niche")

    # ── ledger (reverse) ────────────────────────────────────
    if _col_exists("ledger", "lead_source"):
        op.drop_column("ledger", "lead_source")
    if _col_exists("ledger", "commission_rate_applied"):
        op.drop_column("ledger", "commission_rate_applied")
    if _col_exists("ledger", "deal_model"):
        op.drop_column("ledger", "deal_model")

    # ── users (reverse) ────────────────────────────────────
    if _col_exists("users", "telegram_user_id"):
        op.drop_column("users", "telegram_user_id")
    if _col_exists("users", "level"):
        op.drop_column("users", "level")
    if _col_exists("users", "niches"):
        op.drop_column("users", "niches")

    # ── detected_deals (reverse) ───────────────────────────
    if _col_exists("detected_deals", "platform"):
        op.drop_column("detected_deals", "platform")
    if _col_exists("detected_deals", "market_price_context"):
        op.drop_column("detected_deals", "market_price_context")
    if _col_exists("detected_deals", "ai_draft_message"):
        op.drop_column("detected_deals", "ai_draft_message")
    if _col_exists("detected_deals", "payment_method"):
        op.drop_column("detected_deals", "payment_method")
    if _col_exists("detected_deals", "our_commission_status"):
        op.drop_column("detected_deals", "our_commission_status")
    if _col_exists("detected_deals", "seller_payment_status"):
        op.drop_column("detected_deals", "seller_payment_status")
    if _col_exists("detected_deals", "buyer_payment_status"):
        op.drop_column("detected_deals", "buyer_payment_status")
    if _col_exists("detected_deals", "manager_commission_rate"):
        op.drop_column("detected_deals", "manager_commission_rate")
    if _col_exists("detected_deals", "deal_model"):
        op.drop_column("detected_deals", "deal_model")
    if _col_exists("detected_deals", "niche"):
        op.drop_column("detected_deals", "niche")
    if _col_exists("detected_deals", "lead_source"):
        op.drop_column("detected_deals", "lead_source")

    # ── orders (reverse) ───────────────────────────────────
    if _col_exists("orders", "volume_numeric"):
        op.drop_column("orders", "volume_numeric")
    if _col_exists("orders", "unit"):
        op.drop_column("orders", "unit")
    if _col_exists("orders", "niche"):
        op.drop_column("orders", "niche")
    if _col_exists("orders", "platform"):
        op.drop_column("orders", "platform")
