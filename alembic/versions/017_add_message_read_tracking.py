"""Add read_at to negotiation_messages for read tracking.

Revision ID: 017_add_message_read_tracking
Revises: 016_add_announcements
"""

from typing import Union

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision: str = "017_add_message_read_tracking"
down_revision: Union[str, None] = "016_add_announcements"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c["name"] for c in insp.get_columns(table)]
    return column in columns


def upgrade() -> None:
    if not _column_exists("negotiation_messages", "read_at"):
        op.add_column(
            "negotiation_messages",
            sa.Column(
                "read_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    if _column_exists("negotiation_messages", "read_at"):
        op.drop_column("negotiation_messages", "read_at")
