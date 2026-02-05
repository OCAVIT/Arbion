"""Add chat_title column to raw_messages table

Revision ID: 004_add_raw_messages_chat_title
Revises: 003_add_order_is_active
Create Date: 2026-02-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_add_raw_messages_chat_title"
down_revision: Union[str, None] = "003_add_order_is_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add chat_title column to raw_messages."""
    op.add_column(
        "raw_messages",
        sa.Column("chat_title", sa.String(255), nullable=False, server_default="Unknown")
    )


def downgrade() -> None:
    """Remove chat_title column from raw_messages."""
    op.drop_column("raw_messages", "chat_title")
