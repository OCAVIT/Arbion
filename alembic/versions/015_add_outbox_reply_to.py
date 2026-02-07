"""Add reply_to_message_id to outbox_messages for Telegram reply support.

Revision ID: 015_add_outbox_reply_to
Revises: 014_add_media_file_fields
"""

from typing import Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = "015_add_outbox_reply_to"
down_revision: Union[str, None] = "014_add_media_file_fields"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _col_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade() -> None:
    if not _col_exists("outbox_messages", "reply_to_message_id"):
        op.add_column(
            "outbox_messages",
            sa.Column("reply_to_message_id", sa.BigInteger(), nullable=True),
        )


def downgrade() -> None:
    if _col_exists("outbox_messages", "reply_to_message_id"):
        op.drop_column("outbox_messages", "reply_to_message_id")
