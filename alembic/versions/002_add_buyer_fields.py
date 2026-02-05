"""Add buyer_chat_id and buyer_sender_id to detected_deals

Revision ID: 002_add_buyer_fields
Revises: 001_add_last_active_at
Create Date: 2026-02-05

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_buyer_fields"
down_revision: Union[str, None] = "001_add_last_active_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add buyer contact fields to detected_deals."""
    op.add_column(
        "detected_deals",
        sa.Column("buyer_chat_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "detected_deals",
        sa.Column("buyer_sender_id", sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    """Remove buyer contact fields from detected_deals."""
    op.drop_column("detected_deals", "buyer_sender_id")
    op.drop_column("detected_deals", "buyer_chat_id")
