"""Add file_name to negotiation_messages, media fields to outbox_messages,
and make outbox_messages.message_text nullable.

Revision ID: 014_add_media_file_fields
Revises: 013_add_media_type
"""

from typing import Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = "014_add_media_file_fields"
down_revision: Union[str, None] = "013_add_media_type"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _col_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def upgrade() -> None:
    # negotiation_messages: add file_name
    if not _col_exists("negotiation_messages", "file_name"):
        op.add_column(
            "negotiation_messages",
            sa.Column("file_name", sa.String(255), nullable=True),
        )

    # outbox_messages: make message_text nullable
    op.alter_column(
        "outbox_messages",
        "message_text",
        existing_type=sa.Text(),
        nullable=True,
    )

    # outbox_messages: add media_type
    if not _col_exists("outbox_messages", "media_type"):
        op.add_column(
            "outbox_messages",
            sa.Column("media_type", sa.String(20), nullable=True),
        )

    # outbox_messages: add media_file_path
    if not _col_exists("outbox_messages", "media_file_path"):
        op.add_column(
            "outbox_messages",
            sa.Column("media_file_path", sa.String(500), nullable=True),
        )

    # outbox_messages: add file_name
    if not _col_exists("outbox_messages", "file_name"):
        op.add_column(
            "outbox_messages",
            sa.Column("file_name", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    if _col_exists("outbox_messages", "file_name"):
        op.drop_column("outbox_messages", "file_name")

    if _col_exists("outbox_messages", "media_file_path"):
        op.drop_column("outbox_messages", "media_file_path")

    if _col_exists("outbox_messages", "media_type"):
        op.drop_column("outbox_messages", "media_type")

    op.alter_column(
        "outbox_messages",
        "message_text",
        existing_type=sa.Text(),
        nullable=False,
    )

    if _col_exists("negotiation_messages", "file_name"):
        op.drop_column("negotiation_messages", "file_name")
