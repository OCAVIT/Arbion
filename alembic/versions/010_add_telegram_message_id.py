"""Add telegram_message_id and reply_to_message_id to negotiation_messages

Revision ID: 010_telegram_message_id
Revises: 009_buyer_preferences
Create Date: 2026-02-07

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "010_telegram_message_id"
down_revision: Union[str, None] = "009_buyer_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(table: str, column: str) -> bool:
    """Check if a column already exists (idempotency guard)."""
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade() -> None:
    if not _col_exists("negotiation_messages", "telegram_message_id"):
        op.add_column(
            "negotiation_messages",
            sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        )
    if not _col_exists("negotiation_messages", "reply_to_message_id"):
        op.add_column(
            "negotiation_messages",
            sa.Column("reply_to_message_id", sa.BigInteger(), nullable=True),
        )


def downgrade() -> None:
    if _col_exists("negotiation_messages", "reply_to_message_id"):
        op.drop_column("negotiation_messages", "reply_to_message_id")
    if _col_exists("negotiation_messages", "telegram_message_id"):
        op.drop_column("negotiation_messages", "telegram_message_id")
